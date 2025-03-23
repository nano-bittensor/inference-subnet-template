### Managing Service

This service is responsible for managing: historical scores, rate limits, orchestrating the consume of rate limits.
It exposes a REST API for validator to use:
- Maintain historical scores for each miner hotkey, last N scores.
- Update score for miners
- Consume rate limit:
  - For a specified miner
  - Sampling miner based on the remaining rate limit, used for synthetic scoring loop that requires to validate uniformly across all miners.
  - Sampling miner based on the remaining rate limit, thresholded by top_score_threshold, used for serving organic requests that requires to response from top miners. Representative score for each miner is calculated by averaging the last N scores.

Tools Stack:
- Redis
- Database can be SQLite or Postgres
- SQLAlchemy