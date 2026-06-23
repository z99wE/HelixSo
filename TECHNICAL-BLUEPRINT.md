# HELIX | Technical Architecture Blueprint
### Mathematical Talent Modeling, High-Dimensional Vector Search, and Streamed Ingestion Heuristics

---

## 1. Executive Summary
**HELIX** is an enterprise-grade Talent Genome and Predictive Candidate Ranking Engine. The platform processes large, unstructured candidate profiles, screening out low-yield or inflated resumes, and outputs a rank-ordered shortlist of the top 100 candidates matching natural-language job descriptions. 

By combining **Information Theory (Shannon Entropy)**, **Network Theory (Directed Acyclic Graphs)**, and **High-Dimensional Vector Spaces (FAISS)**, HELIX measures candidate competence, career momentum, and availability intent under strict resource limits ($\le 2\text{ GB}$ peak memory during builds, CPU-only execution, and zero external API dependencies).

---

## 2. Ingestion & Security Filtering (O(1) Gatekeeper)
To protect downstream model metrics from skewed datasets or resume fraud, all incoming profiles must pass through a low-overhead, $O(1)$ rule-based validation layer before scoring:

### A. Temporal Honeypot Heuristic
Resumes claiming unrealistic career durations relative to their physical chronological bounds are flagged. The engine validates:
$$\text{YoE}_{\text{declared}} \le (\text{Current Year} - \text{Earliest Job Start Year}) + 2$$
Any profile violating this inequality (e.g. declaring 15 years of experience but starting their first role in 2020) is immediately pruned.

### B. Profile Inflation Trap
Candidates listing multiple advanced competencies without actual work experience are blocked. The heuristic screens out candidates declaring:
$$\text{Expert-Level Skills} \ge 4 \quad \text{AND} \quad \text{Total Skill Durations} = 0 \text{ months}$$

### C. Outsourcing Firm Exclusion
Profiles with current employment at known high-volume outsourcing networks (e.g., TCS, Infosys, Wipro, Accenture, Cognizant, Capgemini) are filtered out, targeting matches toward candidates showing specialized, product-engineering-centric roles.

---

## 3. Mathematical & Algorithmic Formulations

```
   [Raw Candidate Archive] 
              │
              ▼
    [O(1) Gatekeeper Filters] ──(Flagged)──► [Suppressed / Dropped]
              │
              ▼
   ┌──────────┴─────────────────────────┐
   │       Multidimensional Scoring     │
   ▼                                    ▼
[DAG Promotion Velocity]     [Shannon Entropy Skill Rarity]
   │                                    │
   └──────────┬─────────────────────────┘
              ▼
   [FAISS Semantic Search]
              │
              ▼
   [Linear Blender Normalizer]
              │
              ▼
   [Monotonic Top-100 Shortlist]
```

### A. Skill Rarity Mapping (Shannon Entropy)
Traditional matching engines favor candidates presenting common keywords, causing applicant overflow for standard skill sets. HELIX utilizes a **Shannon Entropy** calculation to identify skill rarity and surface unique "hidden gems":

1. **Global Probability Mapping (Pass 1)**: Streams the candidate database to compute the global probability $P(s)$ for every skill $s$ in the corpus:
   $$P(s) = \frac{\text{Count}(s)}{\sum_{s' \in \text{Global}} \text{Count}(s')}$$
2. **Local Entropy Calculation (Pass 2)**: For each candidate profile carrying a unique subset of skills $S$, the system calculates local information entropy:
   $$H(S) = - \sum_{s \in S} P(s) \log_2 P(s)$$
   Candidates presenting niche, high-demand skill combinations score higher on the rarity index, bringing unique talent profiles to the top of the queue.

### B. Graph-Based Career Trajectory (Directed Acyclic Graph)
Rather than reading career histories as flat, linear text, HELIX models career history as a **Directed Acyclic Graph (DAG)** using `networkx`:
- **Nodes ($V$)**: Represent job titles mapped to a discrete seniority hierarchy (e.g., *Intern = 1, Junior = 2, Mid = 3, Senior = 4, Lead = 5, Director = 6*).
- **Edges ($E$)**: Represent transitions between roles, weighted by the chronological delta in months ($\Delta t$).
- **Promotion Velocity Vector**: For each transition edge, the engine evaluates promotion velocity:
   $$\text{Promotion Velocity} = \frac{V_{\text{target}} - V_{\text{source}}}{\Delta t \text{ (Months)}}$$
   The algorithm extracts the `max_promotion_velocity` and `career_velocity_index` to prioritize professionals who progress rapidly through organizational ranks.

### C. Active Behavioral Intent (Meta Chronos Proxy)
To account for candidate availability, the engine integrates behavioral telemetry:
- Assesses profile update frequencies, recruiter communication rates, and average response times.
- Runs raw response latency ($t$ hours) through a sigmoid penalty curve:
  $$\text{Intent Score} = \text{Response Rate} \times \left( \frac{1}{1 + e^{0.04 \cdot (t - 72)}} \right)$$
  This ensures that outbound recruiting resources are prioritized toward active talent showing a high probability of conversion.

---

## 4. High-Dimensional Vector Search & Scoring
* **Semantic Embeddings**: Candidate histories and job descriptions are converted into 384-dimensional dense vectors using a local `all-MiniLM-L6-v2` Sentence Transformer model.
* **Vector Index**: Stores embeddings in a local **FAISS L2 Flat Index** (`IndexFlatL2`). 
* **Online Querying**:
  1. The natural-language JD is vectorized at runtime.
  2. FAISS performs L2 distance matching, returning candidate IDs and distance metrics.
  3. The final candidate score is computed as a weighted linear combination of the normalized vector similarity ($S_{\text{vec}}$), Shannon Entropy ($H_{\text{entropy}}$), DAG promotion velocity ($V_{\text{dag}}$), and Meta Chronos intent ($I_{\text{intent}}$):
     $$\text{PoS Score} = w_1 \cdot S_{\text{vec}} + w_2 \cdot H_{\text{entropy}} + w_3 \cdot V_{\text{dag}} + w_4 \cdot I_{\text{intent}}$$
  4. The result set is sorted, extracting the top 100 profiles into `team_HelixSo.csv`.

---

## 5. Architectural Footprint & Portability
* **Build Phase**: Executed locally via `build_offline.py` under a 2 GB memory ceiling.
* **Production Sandbox**: `rank.py` runs entirely on CPU with zero network dependencies.
* **Large File Handling**: The 113MB FAISS index is split into 50MB segments (`helix_index.faiss.part-aa/ab/ac`) to bypass GitHub's 100MB commit limit, ensuring the repository is fully portable.
* **Deployment**: The interactive web app is containerized using Docker and deployed on Hugging Face Spaces on port `7860`, running a lightweight Python HTTP server that hosts the interface client-side.
