import os
import sys
import gzip
import json
import math
import pickle
import faiss
import argparse
import csv
import numpy as np
from sentence_transformers import SentenceTransformer

# Re-use the Gatekeeper logic to ensure we match the exact candidate indices
class VerifyProfileIntegrity:
    def __init__(self):
        self.banned_companies = {'tcs', 'infosys', 'wipro', 'accenture', 'cognizant', 'capgemini'}

    def is_valid(self, candidate):
        profile = candidate.get('profile', {})
        years_of_experience = profile.get('years_of_experience', 0)
        if years_of_experience is None: years_of_experience = 0
            
        career_history = candidate.get('career_history', [])
        if career_history:
            earliest_year = 9999
            for job in career_history:
                start_date = job.get('start_date')
                if start_date:
                    try:
                        year = int(start_date.split('-')[0])
                        if year < earliest_year: earliest_year = year
                    except ValueError: pass
            if earliest_year != 9999:
                delta = 2026 - (earliest_year - 2)
                if years_of_experience > delta: return False
                    
        skills = candidate.get('skills', [])
        expert_skills = [s for s in skills if s.get('proficiency') == 'expert']
        if len(expert_skills) >= 4:
            if all(s.get('duration_months', -1) == 0 for s in expert_skills): return False
                
        current_company = profile.get('current_company')
        if current_company:
            current_company = current_company.lower()
            if any(banned in current_company for banned in self.banned_companies): return False
            
        return True

def generate_reasoning(meta):
    # Dynamic reasoning generator
    yoe = meta.get('years_of_experience', 0)
    title = meta.get('current_title', 'Professional')
    hidden_gem = meta.get('Hidden_Gem_Index_Score', 0)
    intent = meta.get('Intent_Score', 0)
    
    strength = f"Strong fit with {yoe} years of velocity-driven experience as a {title}, coupled with "
    if hidden_gem > 3.0:
        strength += "exceptionally high structural skill entropy."
    else:
        strength += "solid foundational expertise."
        
    concern = " Concern: "
    if intent < 0.5:
        concern += "Activity intent score is slightly degraded due to recent inactivity."
    else:
        concern += "May require competitive compensation to match high engagement trajectory."
        
    return strength + concern

def run_ranking(candidates_path, output_path):
    # 1. Load Pre-computed Data
    print("Loading pre-computed artifacts...")
    
    # Auto-reconstruct FAISS index from split parts if missing
    if not os.path.exists('helix_index.faiss'):
        parts = ['helix_index.faiss.part-aa', 'helix_index.faiss.part-ab', 'helix_index.faiss.part-ac']
        if all(os.path.exists(p) for p in parts):
            print("Reconstructing FAISS index from split parts...")
            with open('helix_index.faiss', 'wb') as outfile:
                for part in parts:
                    with open(part, 'rb') as infile:
                        outfile.write(infile.read())
            print("FAISS index reconstructed successfully.")
            
    with open('candidate_metadata.pkl', 'rb') as f:
        metadata = pickle.load(f)
        
    index = faiss.read_index('helix_index.faiss')
    
    # 2. Embed JD for Dense Scoring
    jd_vocab = {
        "embeddings", "retrieval", "ranking", "vector database", "faiss", 
        "pinecone", "llm", "fine-tuning", "lora", "qlora", "peft", 
        "xgboost", "learning-to-rank", "ndcg", "mrr", "nlp"
    }
    jd_text = " ".join(jd_vocab)
    
    print("Embedding Job Description...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    jd_emb = model.encode([jd_text], convert_to_numpy=True)
    
    # We query all candidates in the index to get their distances
    # For FlatL2, lower distance = higher similarity.
    k = index.ntotal
    D, I = index.search(jd_emb, k)
    
    # Create an array of dense scores mapped by original index
    dense_scores = np.zeros(k)
    max_dist = np.max(D[0])
    # Invert distance to score (0 to 1 scaling, roughly)
    for idx, (dist, idx_match) in enumerate(zip(D[0], I[0])):
        dense_scores[idx_match] = 1.0 - (dist / (max_dist + 1e-9))
        
    # 3. Stream candidates for Sparse Score
    print("Streaming candidates for Sparse Scoring...")
    verifier = VerifyProfileIntegrity()
    passed_idx = 0
    final_results = []
    
    open_func = gzip.open if candidates_path.endswith('.gz') else open
    
    with open_func(candidates_path, 'rt', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            candidate = json.loads(line)
            
            if verifier.is_valid(candidate):
                # Ensure we don't exceed metadata length
                if passed_idx >= len(metadata):
                    break
                    
                meta = metadata[passed_idx]
                dense_score = dense_scores[passed_idx]
                
                profile = candidate.get('profile', {})
                skills = candidate.get('skills', [])
                
                headline = profile.get('headline', '').lower()
                summary = profile.get('summary', '').lower()
                skills_text = " ".join([s.get('name', '').lower() for s in skills if s.get('name')])
                combined_text = f"{headline} {summary} {skills_text}"
                
                # Sparse Score
                overlap = sum(1 for term in jd_vocab if term in combined_text)
                sparse_score = overlap / len(jd_vocab)
                
                semantic_fit = (0.5 * dense_score) + (0.5 * sparse_score)
                
                career_vel = meta.get('Career_Velocity_Vector', {})
                max_vel = career_vel.get('max_promotion_velocity', 0.0)
                
                intent = meta.get('Intent_Score', 0.0)
                hidden_gem = meta.get('Hidden_Gem_Index_Score', 0.0)
                
                # Deep-Tech Ranking Math
                final_score = (0.40 * semantic_fit + 0.10 * max_vel) * (0.25 * intent + 0.25 * hidden_gem)
                
                meta['final_score'] = final_score
                final_results.append(meta)
                
                passed_idx += 1

    print("Sorting results...")
    # Round scores first to ensure sorting is aligned with output precision
    for res in final_results:
        res['rounded_score'] = round(res['final_score'], 4)
    # Sort descending by rounded score, ascending by candidate_id
    final_results.sort(key=lambda x: (-x['rounded_score'], x['candidate_id']))
    
    top_100 = final_results[:100]
    
    print(f"Exporting Top 100 to {output_path}...")
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['candidate_id', 'rank', 'score', 'reasoning'])
        
        for rank, res in enumerate(top_100, 1):
            cand_id = res['candidate_id']
            score = res['rounded_score']
            reasoning = generate_reasoning(res)
            writer.writerow([cand_id, rank, score, reasoning])
            
    print("Execution complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HELIX Execution Engine Ranker")
    parser.add_argument('--candidates', required=True, help='Path to candidates input file')
    parser.add_argument('--out', required=True, help='Path to output csv file')
    
    args = parser.parse_args()
    run_ranking(args.candidates, args.out)
