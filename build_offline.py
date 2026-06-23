import gzip
import json
import math
import pickle
import faiss
import networkx as nx
import numpy as np
from datetime import datetime
from collections import defaultdict
from scipy.stats import entropy
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

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
                        if year < earliest_year:
                            earliest_year = year
                    except ValueError:
                        pass
            if earliest_year != 9999:
                delta = 2026 - (earliest_year - 2)
                if years_of_experience > delta:
                    return False
                    
        skills = candidate.get('skills', [])
        expert_skills = [s for s in skills if s.get('proficiency') == 'expert']
        if len(expert_skills) >= 4:
            if all(s.get('duration_months', -1) == 0 for s in expert_skills):
                return False
                
        current_company = profile.get('current_company')
        if current_company:
            current_company = current_company.lower()
            if any(banned in current_company for banned in self.banned_companies):
                return False
            
        return True

def get_seniority_level(title):
    title = title.lower() if title else ""
    if any(x in title for x in ['intern', 'trainee', 'student']):
        return 1
    if any(x in title for x in ['junior', 'associate', 'entry']):
        return 2
    if any(x in title for x in ['senior', 'sr', 'staff', 'principal', 'lead']):
        return 4
    if any(x in title for x in ['manager', 'director', 'vp', 'head', 'chief', 'ceo', 'cto']):
        return 5
    return 3 # Mid level by default

def calculate_career_velocity(career_history):
    if not career_history or len(career_history) < 2:
        return {'max_promotion_velocity': 0.0, 'avg_time_in_role_months': 0.0}
        
    G = nx.DiGraph()
    
    # Sort history chronologically
    sorted_jobs = []
    for job in career_history:
        start_date = job.get('start_date')
        if start_date:
            try:
                dt = datetime.strptime(start_date, '%Y-%m-%d')
                sorted_jobs.append((dt, job))
            except ValueError:
                pass
    sorted_jobs.sort(key=lambda x: x[0])
    
    velocities = []
    total_months = 0
    roles_count = len(sorted_jobs)
    
    for i in range(len(sorted_jobs)):
        dt_i, job_i = sorted_jobs[i]
        title_i = job_i.get('title', '')
        sen_i = get_seniority_level(title_i)
        duration_i = job_i.get('duration_months') or 0
        total_months += duration_i
        
        G.add_node(i, title=title_i, seniority=sen_i, duration=duration_i)
        
        if i > 0:
            dt_prev, job_prev = sorted_jobs[i-1]
            sen_prev = get_seniority_level(job_prev.get('title', ''))
            
            # Months between starts
            delta_months = max(1, (dt_i - dt_prev).days / 30.0)
            sen_delta = max(0, sen_i - sen_prev)
            
            velocity = sen_delta / delta_months
            velocities.append(velocity)
            G.add_edge(i-1, i, weight=velocity)
            
    max_velocity = max(velocities) if velocities else 0.0
    avg_time = total_months / roles_count if roles_count > 0 else 0.0
    
    return {'max_promotion_velocity': max_velocity, 'avg_time_in_role_months': avg_time}

def process_candidates():
    input_file = 'candidates.jsonl.gz'
    output_file = 'candidate_metadata.pkl'
    index_file = 'helix_index.faiss'
    
    print("Pass 1: Computing global skill frequencies...")
    skill_counts = defaultdict(int)
    total_skills = 0
    
    try:
        with gzip.open(input_file, 'rt', encoding='utf-8') as f:
            for line in tqdm(f, desc="Pass 1: Streaming"):
                line = line.strip()
                if not line: continue
                candidate = json.loads(line)
                for s in candidate.get('skills', []):
                    name = s.get('name')
                    if name:
                        skill_counts[name.lower()] += 1
                        total_skills += 1
    except FileNotFoundError:
        print(f"Error: {input_file} not found.")
        return

    # Compute global probabilities
    skill_probs = {k: v / total_skills for k, v in skill_counts.items()}
    
    print("Pass 2: Applying Gatekeeper, Information/Network Theory models, and LLM Embeddings...")
    verifier = VerifyProfileIntegrity()
    passed_candidates = []
    
    reference_date = datetime(2026, 6, 23)
    
    model = SentenceTransformer('all-MiniLM-L6-v2')
    embedding_dim = model.get_sentence_embedding_dimension()
    index = faiss.IndexFlatL2(embedding_dim)
    
    batch_texts = []
    
    with gzip.open(input_file, 'rt', encoding='utf-8') as f:
        for idx, line in enumerate(tqdm(f, desc="Pass 2: Streaming")):
            line = line.strip()
            if not line: continue
            candidate = json.loads(line)
            
            if verifier.is_valid(candidate):
                profile = candidate.get('profile', {})
                redrob_signals = candidate.get('redrob_signals', {})
                skills = candidate.get('skills', [])
                career_history = candidate.get('career_history', [])
                
                candidate_id = candidate.get('candidate_id')
                current_title = profile.get('current_title')
                years_of_experience = profile.get('years_of_experience')
                
                # Information Theory: Shannon Entropy of candidate's skills
                candidate_skill_probs = []
                for s in skills:
                    name = s.get('name')
                    if name and name.lower() in skill_probs:
                        candidate_skill_probs.append(skill_probs[name.lower()])
                
                hidden_gem_index_score = 0.0
                if candidate_skill_probs:
                    norm_factor = sum(candidate_skill_probs)
                    norm_probs = [p / norm_factor for p in candidate_skill_probs]
                    hidden_gem_index_score = float(entropy(norm_probs))
                    avg_rarity = -1.0 * sum(math.log2(p) for p in candidate_skill_probs) / len(candidate_skill_probs)
                    hidden_gem_index_score += float(avg_rarity)
                
                # Network Theory: DAG Career Velocity
                career_velocity_vector = calculate_career_velocity(career_history)
                
                # Chronos Proxy
                recruiter_response_rate = redrob_signals.get('recruiter_response_rate')
                if recruiter_response_rate is None: recruiter_response_rate = 0.0
                
                avg_response_time_hours = redrob_signals.get('avg_response_time_hours')
                if avg_response_time_hours is None: avg_response_time_hours = 72.0
                
                last_active_date_str = redrob_signals.get('last_active_date')
                
                latency_penalty = 1.0 / (1.0 + math.exp(0.04 * (avg_response_time_hours - 72.0)))
                
                decay_factor = 1.0
                if last_active_date_str:
                    try:
                        last_active_date = datetime.strptime(last_active_date_str, '%Y-%m-%d')
                        days_since_active = (reference_date - last_active_date).days
                        decay_factor = math.exp(-0.01 * max(0, days_since_active))
                    except ValueError:
                        pass
                        
                intent_score = recruiter_response_rate * latency_penalty * decay_factor
                
                passed_candidates.append({
                    'candidate_id': candidate_id,
                    'Intent_Score': intent_score,
                    'Hidden_Gem_Index_Score': hidden_gem_index_score,
                    'Career_Velocity_Vector': career_velocity_vector,
                    'years_of_experience': years_of_experience,
                    'current_title': current_title
                })
                
                # Text for embedding
                headline = profile.get('headline') or ''
                summary = profile.get('summary') or ''
                skills_text = ", ".join([s.get('name', '') for s in skills if s.get('name')])
                combined_text = f"{headline} {summary} {skills_text}".strip()
                
                if not combined_text:
                    combined_text = "No details provided"
                    
                batch_texts.append(combined_text)
                
                # Embed in batches of 256
                if len(batch_texts) >= 256:
                    embeddings = model.encode(batch_texts, convert_to_numpy=True)
                    index.add(embeddings)
                    batch_texts.clear()
                    
    # Process remaining batch
    if batch_texts:
        embeddings = model.encode(batch_texts, convert_to_numpy=True)
        index.add(embeddings)
        batch_texts.clear()
        
    print(f"Pass 2 complete. Valid profiles extracted: {len(passed_candidates)}")
    print(f"Serializing metadata to {output_file}...")
    
    with open(output_file, 'wb') as f:
        pickle.dump(passed_candidates, f)
        
    print(f"Writing FAISS index to {index_file}...")
    faiss.write_index(index, index_file)
    print("Done.")

if __name__ == "__main__":
    process_candidates()
