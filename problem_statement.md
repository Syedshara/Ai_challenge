# 📋 Problem Statement — In Simple Words

> *What are we building, why does it exist, and who needs it?*

---

## 🏢 The Real-World Scenario

Imagine you work at an **insurance company**.

Your software manages millions of insurance policies — people's car insurance, home insurance, health insurance, and more.

Every time someone does something — checks their policy, files a claim, updates their address — your software **asks the database a question**. That question is written in a language called **SQL**.

Now imagine this happens one afternoon:

```
☀️  Morning   →  Database answers in 1 second     ✅ Everything is fine
🌅  Afternoon →  Database answers in 50 seconds   ❌ Something is very wrong
```

Customers are waiting on hold. Insurance agents are frozen at their screens. The business is losing money every minute. Someone needs to figure out:

- **Why** did it suddenly get slow?
- **What** is the root cause?
- **How** do we fix it — right now?

Normally, a **senior Database Engineer (DBA)** does this job. They dig through logs, read SQL code, spot the problem, and fix it. It can take hours. It requires deep expertise. And not every team has one available 24/7.

**This system replaces that manual investigation with an AI that does it in seconds.**

---

## 🔍 The 3 Core Questions This AI Answers

| Question | Example Answer |
|----------|---------------|
| **"Why is this query slow?"** | "This query reads all 50 million rows because there is no filter (WHERE clause)" |
| **"How do I fix it?"** | "Add this specific index and rewrite the query like this..." |
| **"Is this an anomaly?"** | "Yes — this query normally takes 1 second. It now takes 50 seconds. Something broke at 2:14 PM." |

---

## 🧱 The Actual Problems Being Detected

Think of it like a doctor diagnosing symptoms in a patient:

| Symptom (What You See) | Disease (Root Cause) | Medicine (The Fix) |
|------------------------|---------------------|--------------------|
| Query takes 2,469 seconds | Reading the entire table — no filter applied | Add a `WHERE` clause |
| JSON field filter takes 25 seconds | Database cannot use an index on JSON fields | Add a generated column + index |
| Fast query but runs 10,000 times/day | No caching — hitting the database too often | Add a Redis cache layer |
| 3 tables joined with JSON processing | Multiplied complexity with no optimization | Use a materialized view |
| Latency jumped from 1s → 50s suddenly | Anomaly — lock contention, bad data, or missing index | Alert + investigate |

Each of these is a **real pattern** that happens in insurance software systems. Our AI knows all of them, retrieves similar past cases, and explains them in plain language.

---

## 👤 Who Uses This System?

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  👨‍💻  Developer                                                   │
│      "I wrote this SQL query. Why is it slow?"                   │
│       → Gets instant diagnosis + a corrected rewritten SQL       │
│                                                                  │
│  🔧  Database Admin (DBA)                                        │
│      "Show me what is wrong with today's slow queries"           │
│       → Gets root cause + specific CREATE INDEX statements       │
│                                                                  │
│  🚨  Ops / DevOps Engineer                                       │
│      "Our API is suddenly timing out — what happened?"           │
│       → Anomaly detector flags the spike with timestamp          │
│                                                                  │
│  🏢  Insurance Business / Product Team                           │
│      "Why are agents waiting 30 seconds per screen load?"        │
│       → System traces it back to one poorly written query        │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🤔 Why Is This Hard Without AI?

| Without This System | With This System |
|---------------------|-----------------|
| A DBA manually reads slow query logs | AI reads and explains it in seconds |
| Takes hours to find the root cause | Takes under 1 second |
| Only expert DBAs can diagnose it | Any developer can ask in plain English |
| No memory of past incidents | RAG retrieves similar historical cases |
| Anomalies noticed only when users complain | Detected automatically from metrics |
| Fix is vague ("add an index somewhere") | Fix is exact: `CREATE INDEX idx_policy_status ON policy_data(status)` |
| Every incident starts from scratch | System learns from past feedback |

---

## 🏦 Why Insurance Specifically?

Insurance companies face a unique combination of challenges that make database performance critical:

**1. Massive Data Volume**
Insurance companies store millions of policies, claims, payments, and audit logs. A single `policy_data` table can have 50+ million rows. One badly written query can bring the whole system to a halt.

**2. Complex JSON Data**
Modern insurance platforms store flexible policy configurations as JSON. Filtering on JSON fields (`JSON_EXTRACT`) is extremely slow without special handling. This is one of the most common performance traps in insurance software.

**3. High-Stakes Real Time**
When a customer calls after a car accident, the agent needs to pull up their policy instantly. A 30-second delay is not just annoying — it is a failure of service at a critical moment.

**4. Legacy SQL Everywhere**
Insurance platforms often have SQL queries written years or decades ago by engineers who no longer work there. Nobody fully understands them. The AI can read and diagnose them even when the original author is gone.

**5. Strict Compliance**
Insurance is heavily regulated. Changes to data systems require understanding and documentation. The AI's explanation chains provide that documentation automatically.

---

## 🧠 What Is RAG and Why Do We Need It?

**RAG = Retrieval Augmented Generation**

Without RAG, an AI gives you generic advice based only on its training data.
With RAG, the AI first searches your own knowledge base of past incidents before answering.

```
─────────────────────────────────────────────────────────────
WITHOUT RAG                       WITH RAG
─────────────────────────────────────────────────────────────

You ask:                          You ask:
"Why is this query slow?"         "Why is this query slow?"
        │                                   │
        ▼                                   ▼
AI uses only its               AI first searches past cases:
general knowledge              "We saw this exact pattern
                                in Case 002 last month.
                                JSON_EXTRACT with no index.
Result:                         Here is exactly what fixed it."
"Maybe add an index?"
(vague, generic)               Result:
                                "Add a generated column and
                                 index — here is the SQL."
                                (specific, proven, contextual)
─────────────────────────────────────────────────────────────
```

The AI stores past cases in a **vector database** (ChromaDB). When you ask a question, it finds the most similar past cases using **semantic search** (meaning-based, not just keyword matching) and uses those as context before generating its answer.

---

## 🔄 The Full System Flow — Step by Step

```
You type:
"Why is SELECT * FROM policy_data taking 40 minutes?"
                          │
                          ▼
              ┌───────────────────────┐
              │  Step 1: Understand   │
              │  What does the user   │
              │  actually want?       │
              │  → "query_analysis"   │
              └───────────┬───────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │  Step 2: Extract SQL  │
              │  Pull out the actual  │
              │  SQL from the question│
              └───────────┬───────────┘
                          │
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
  ┌──────────────┐ ┌─────────────┐ ┌──────────────────┐
  │ Step 3: RAG  │ │ Step 4:     │ │ Step 5: Anomaly  │
  │              │ │ Rule Engine │ │ Detection        │
  │ Search past  │ │             │ │                  │
  │ cases for    │ │ Scan SQL    │ │ Check if metrics │
  │ similar      │ │ for known   │ │ show unusual     │
  │ patterns     │ │ anti-       │ │ spike or trend   │
  │              │ │ patterns    │ │                  │
  │ Found:       │ │ Found:      │ │ Result:          │
  │ case_001     │ │ SELECT *    │ │ Not applicable   │
  │ (94% match)  │ │ No WHERE    │ │ here             │
  └──────┬───────┘ └──────┬──────┘ └──────────────────┘
         │                │
         └───────┬────────┘
                 ▼
      ┌───────────────────────┐
      │  Step 6: LLM combines │
      │  everything together  │
      │  into one clear answer│
      └───────────┬───────────┘
                  │
                  ▼
      ┌───────────────────────┐
      │  Step 7: Rewrite SQL  │
      │  Output corrected     │
      │  query ready to use   │
      └───────────┬───────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│                                                 │
│  🔴 Problem:    Full table scan, no filtering   │
│                                                 │
│  📋 Root Cause: No WHERE clause forces the      │
│                 database to read all 50 million │
│                 rows. SELECT * also fetches     │
│                 heavy JSON columns you don't    │
│                 need.                           │
│                                                 │
│  ✅ Rewritten SQL:                              │
│     SELECT policy_id,                           │
│            premium_amount,                      │
│            state,                               │
│            status                               │
│     FROM   policy_data                          │
│     WHERE  status = 'ACTIVE'                    │
│     LIMIT  100 OFFSET 0;                        │
│                                                 │
│  🔑 Add this index:                             │
│     CREATE INDEX idx_policy_status              │
│     ON policy_data(status);                     │
│                                                 │
│  📊 Confidence: 95%                             │
│  ⚠️  Severity:   CRITICAL                       │
│  📎 Similar Cases: case_001, case_007           │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## 🤖 What Makes This System Smart?

This is not a simple chatbot that just looks up answers. It has multiple layers working together:

| Layer | What It Does | Why It Matters |
|-------|-------------|----------------|
| **Rule Engine** | Scans SQL for known anti-patterns using logic | Fast, deterministic, always right |
| **RAG (Vector Search)** | Finds similar past cases by meaning | Contextual, learns from history |
| **LLM (Language Model)** | Combines everything into a clear explanation | Human-readable, nuanced reasoning |
| **Anomaly Detector** | Watches metrics for statistical spikes | Catches problems before users do |
| **Query Rewriter** | Outputs the actual corrected SQL | Actionable — not just advice |
| **Learning Loop** | Improves from user feedback over time | Gets smarter with every use |
| **A/B Testing** | Tests two fix strategies, measures which works better | Evidence-based improvement |

---

## 💡 One Line Summary

> *"We are building an AI that acts like a senior database doctor — you show it a sick SQL query, it diagnoses the problem, explains why it is broken, and hands you the corrected SQL ready to use — all in under a second."*

---

*Part of the AI Engineering 3-Day Challenge — Insurance Policy Administration System (PAS)*


 