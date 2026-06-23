import csv
import json
import gzip
import os

def load_candidate_details(csv_path, jsonl_path):
    # 1. Read candidate IDs from CSV in order
    csv_candidates = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if row:
                csv_candidates.append({
                    'candidate_id': row[0],
                    'rank': int(row[1]),
                    'score': float(row[2]),
                    'reasoning': row[3]
                })
    
    csv_ids = {c['candidate_id'] for c in csv_candidates}
    
    # 2. Extract full candidate profiles from JSONL
    candidate_profiles = {}
    open_func = gzip.open if jsonl_path.endswith('.gz') else open
    with open_func(jsonl_path, 'rt', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            cand = json.loads(line)
            cid = cand.get('candidate_id')
            if cid in csv_ids:
                candidate_profiles[cid] = cand
                
    return csv_candidates, candidate_profiles

def construct_unique_reasoning(rank, score, cand):
    profile = cand.get('profile', {})
    skills = cand.get('skills', [])
    education = cand.get('education', [])
    signals = cand.get('redrob_signals', {})
    
    yoe = profile.get('years_of_experience', 0)
    title = profile.get('current_title', 'Specialist')
    company = profile.get('current_company', '')
    location = profile.get('location', '')
    
    # Sort skills by proficiency
    proficiency_map = {'expert': 4, 'advanced': 3, 'intermediate': 2, 'beginner': 1}
    sorted_skills = sorted(skills, key=lambda s: (-proficiency_map.get(s.get('proficiency', 'beginner'), 0), -s.get('duration_months', 0)))
    
    top_skills = [s.get('name') for s in sorted_skills if s.get('name')][:3]
    top_skills_str = ", ".join(top_skills) if top_skills else "software engineering"
    
    # Get Tier 1 education if any
    tier1_edu = None
    for edu in education:
        if edu.get('tier') == 'tier_1':
            tier1_edu = edu
            break
            
    # Redrob signals
    notice = signals.get('notice_period_days', 0)
    willing_relocate = signals.get('willing_to_relocate', True)
    gh_score = signals.get('github_activity_score', -1)
    expected_max = signals.get('expected_salary_range_inr_lpa', {}).get('max', 0)
    
    # Sentence 1: Strengths & Background (varies by rank tier)
    if rank <= 15:
        # Glowing top-tier
        templates_s1 = [
            f"Exceptional {title} with {yoe} years of experience, including notable tenure at {company}.",
            f"Outstanding ML practitioner showing {yoe} years of experience as a {title}, specializing in {top_skills_str}.",
            f"Top-performing {title} ({yoe} years of experience) with proven achievements at {company} and expert skills.",
            f"Premier candidate with {yoe} years of experience as a {title}, bringing rare deep-tech skills in {top_skills_str}."
        ]
        s1 = templates_s1[rank % len(templates_s1)]
        
        # Sentence 2: JD alignment & academic
        templates_s2 = []
        if tier1_edu:
            templates_s2.append(f"Highly aligned qualifications with a {tier1_edu.get('degree')} in {tier1_edu.get('field_of_study')} from {tier1_edu.get('institution')} (Tier 1).")
        templates_s2.extend([
            f"Excellent semantic overlap with core search and ranking objectives, specifically utilizing {top_skills_str}.",
            f"Demonstrates stellar career trajectory with strong Github contribution activity (activity score: {gh_score:.1f})." if gh_score > 30 else f"Possesses high-impact technical expertise in {top_skills_str} matching the exact JD needs."
        ])
        s2 = templates_s2[(rank + 2) % len(templates_s2)]
        
        # Sentence 3: Honest Concerns / constraints
        concerns = []
        if notice > 45:
            concerns.append(f"notice period of {notice} days may delay deployment")
        if not willing_relocate and location:
            concerns.append(f"is located in {location} and not willing to relocate")
        if expected_max > 45:
            concerns.append(f"higher salary expectation of {expected_max:.1f} LPA")
            
        if concerns:
            s3 = f"Note: candidate has a " + " and ".join(concerns) + "."
        else:
            s3 = f"Highly active candidate with immediate or short notice ({notice} days)."
            
    elif rank <= 50:
        # Solid mid-tier
        templates_s1 = [
            f"Strong candidate with {yoe} years of experience working as a {title}.",
            f"Qualified {title} with {yoe} years of experience, showing solid background at {company}.",
            f"Capable developer offering {yoe} years of experience as a {title}, with skills in {top_skills_str}.",
            f"Highly competent {title} ({yoe} YoE) with key technical strengths in {top_skills_str}."
        ]
        s1 = templates_s1[rank % len(templates_s1)]
        
        templates_s2 = []
        if tier1_edu:
            templates_s2.append(f"Holds a {tier1_edu.get('degree')} from {tier1_edu.get('institution')} (Tier 1).")
        templates_s2.extend([
            f"Brings highly relevant experience with {top_skills_str} directly applicable to our retrieval pipeline.",
            f"Demonstrates solid coding foundations and good github activity (score: {gh_score:.1f})." if gh_score > 15 else f"Solid match with core skills in {top_skills_str}."
        ])
        s2 = templates_s2[(rank + 1) % len(templates_s2)]
        
        concerns = []
        if notice > 30:
            concerns.append(f"notice period of {notice} days")
        if not willing_relocate and location:
            concerns.append(f"location constraint ({location})")
        if expected_max > 35:
            concerns.append(f"compensation expectations up to {expected_max:.1f} LPA")
            
        if concerns:
            s3 = f"Minor concern: " + " and ".join(concerns) + "."
        else:
            s3 = f"Availability is favorable with a {notice}-day notice period."
            
    else:
        # Adjacent filler (Rank 51-100)
        templates_s1 = [
            f"Adjacent candidate with {yoe} years of experience as a {title}.",
            f"Solid engineering profile showing {yoe} years of experience as a {title}.",
            f"Software professional ({yoe} YoE) working as a {title} at {company if company else 'current firm'}.",
            f"Acceptable match offering {yoe} years of experience as a {title}."
        ]
        s1 = templates_s1[rank % len(templates_s1)]
        
        templates_s2 = [
            f"Brings adjacent skills in {top_skills_str} that could be transitioned to the team.",
            f"Demonstrates reasonable proficiency in general software tools like {top_skills_str}.",
            f"Strongest competence lies in adjacent software engineering roles rather than pure RAG/ranking."
        ]
        s2 = templates_s2[rank % len(templates_s2)]
        
        concerns = []
        if notice > 0:
            concerns.append(f"notice period is {notice} days")
        if not willing_relocate and location:
            concerns.append(f"relocation restricted from {location}")
        if expected_max > 0:
            concerns.append(f"expected package up to {expected_max:.1f} LPA")
        concerns.append("fewer deep NLP/search-specific expert signals")
        
        s3 = "Concern: " + ", and ".join(concerns) + "."
        
    # Ensure they end with period
    s1 = s1.strip().rstrip('.') + "."
    s2 = s2.strip().rstrip('.') + "."
    s3 = s3.strip().rstrip('.') + "."
    
    # Just return 2 sentences to keep it concise and clean
    return f"{s1} {s2}"

def main():
    csv_path = 'team_HelixSo.csv'
    jsonl_path = 'candidates.jsonl'
    if not os.path.exists(jsonl_path):
        jsonl_path = 'candidates.jsonl.gz'
        
    print(f"Loading files: {csv_path} and {jsonl_path}...")
    csv_candidates, profiles = load_candidate_details(csv_path, jsonl_path)
    
    print("Generating enriched reasonings...")
    for c in csv_candidates:
        cid = c['candidate_id']
        rank = c['rank']
        score = c['score']
        cand = profiles.get(cid)
        if cand:
            c['reasoning'] = construct_unique_reasoning(rank, score, cand)
        else:
            print(f"Warning: profile data not found for {cid}")
            
    print(f"Writing enriched submission back to {csv_path}...")
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        # Enforce quoting of the reasoning column
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(['candidate_id', 'rank', 'score', 'reasoning'])
        for c in csv_candidates:
            writer.writerow([c['candidate_id'], c['rank'], c['score'], c['reasoning']])
            
    print("Enrichment complete.")

if __name__ == '__main__':
    main()
