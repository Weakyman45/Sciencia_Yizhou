# Potential Data Sources

## 1) amazon_us_reviews (Hugging Face dataset)

Source: https://huggingface.co/datasets/polinaeterna/amazon_us_reviews

- **Feasibility at scale:** High feasibility for bulk ingestion, but scale is capped at the snapshot date.
- **Long-term maintainability:** High stability of access method, but data volume is large, so maintenance is a challenge.
- **Data richness and modeling value:** Rich for downstream analysis. Besides stars and text, `review_date` supports temporal analysis, `helpful_votes` reflects community validation, and `marketplace` can support geographical analysis.
- **Bias and representativeness:** Reviews skew toward Amazon users who are motivated to post.
- **Trade-offs versus live collection:** Using this dataset solves the immediate need for training data but leaves us with no real “ingestion process” to build.

---

## 2) Reddit

- **Long-term maintainability:** API policies might change, but using the official API is generally more stable and trustworthy.
- **Feasibility at scale:** 100 queries/min is not enough for collecting very large-scale historical data. The advantage of Reddit as a live data stream is that we can poll new posts/comments per subreddit or track keywords daily/hourly.
- **Data richness and modeling value:** Timestamps are available. Upvotes/downvotes can be used as weak signals for sentiment analysis, but they measure popularity as much as sentiment. Most importantly, Reddit offers **deep, nested threaded debates**, allowing us to model how sentiment evolves in a conversation.
- **Bias and representativeness:** Reddit is heavily community-structured; each subreddit is its own culture and demographic skew.
- **Trade-offs versus live collection:** Reddit is a good candidate when prioritizing recurring data streams and pipeline durability.

---

## 3) Bluesky

- **Long-term maintainability:** The protocol is designed to be open and sync-friendly, which helps long-term.
- **Feasibility at scale:** Bluesky exposes a “Firehose” via WebSocket, making it technically feasible to ingest large volumes of public data in real time.
- **Data richness and modeling value:** While excellent for capturing real-time reactions, it lacks the explicit 1–5 star ratings of Amazon and the nested depth of Reddit. The main advantage is rich behavioral signals like posts, likes, follows, etc.
- **Bias and representativeness:** The user base might be skewed. I hadn’t heard about this platform before this project, and none of my friends use it (as far as I know).
- **Trade-offs versus live collection:** Similar to Reddit, Bluesky is a good candidate when considering recurring data streams and pipeline durability.

---

## 4) Movie Review Dataset (Stanford)

Source: https://ai.stanford.edu/~amaas/data/sentiment/

- **Long-term maintainability:** Stable download and stable format.
- **Feasibility at scale:** Fixed size (25,000 training + 25,000 test), low feasibility at scale.
- **Data richness and modeling value:** Clear binary labels, but limited metadata, no stars, and no user/product structure.
- **Bias and representativeness:** Skewed toward the movie-review domain.
- **Trade-offs versus live collection:** Easiest path to demo a classifier, but doesn’t demonstrate ingestion challenges.

---

# Conclusion

I first want to exclude the Stanford movie review dataset and the Amazon review dataset because they are static.

While Bluesky is strong in long-term maintainability and feasibility at scale, it currently lacks the semantic depth required for high-quality sentiment modeling. It lacks explicit ratings and, critically, lacks the nested threaded debates necessary to analyze how sentiment evolves in a conversation. I am also concerned that the user base might be skewed, given that I have not seen many people using it.

So, I would personally suggest **Reddit** as our data source. It offers the highest data richness and modeling value. The combination of upvotes, timestamps, and deep conversation trees allows us to meet the project goal of understanding how users think, feel, and behave better. The main trade-off is the 100 queries per minute rate limit, but I don’t think it is a deal-breaker.
