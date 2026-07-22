# newsletter_ny
Daily Cultur NL for New York City



Overview
It sounded like a simple project: scrape a few event details, automatically format the content, and create a personal newsletter for private use.

What actually happened was hours of endless coding. The project got lost in the depths of error messages, hit numerous dead ends, and ultimately crashed against the firewalls and security measures of event platforms.

Furthermore, it became clear throughout the process that many underground newsletters have unusual structures and are technically difficult to parse. Their operators frequently change the layout, which quickly renders automated scrapers useless. Scraping data directly from individual venues worked in some places, but failed to deliver the expected, reliable results.



Technical Goals and Planned Architecture
The goal was to build a multi-stage data pipeline for underground events in New York City:

Data Ingestion: Aggregating event data from various sources such as Resident Advisor, DICE, Oh My Rockness, and NYC Noise.

Data Cleaning and Deduplication: Merging, filtering, and cleaning raw data using Pandas.

Content Curation: Relevance scoring and automated generation of German descriptions in an informal tone using the OpenAI API (GPT-4o).

HTML Rendering: Generating a structured HTML newsletter for direct browser viewing.



Technical Insights and Debugging
Unofficial and Outdated Endpoints (DICE API)
The DICE API endpoint returned a persistent HTTP status 404 (Not Found). Unofficial APIs provided by commercial vendors change without notice. After a systematic analysis using isolated scripts, the endpoint was removed from the pipeline.

Dynamic GraphQL Schemas (Resident Advisor)
Requests to Resident Advisor's GraphQL interface led to validation errors or unhandled exceptions in the Python code. By using introspection queries (type queries via __type), valid parameters such as type: FROMDATE were identified. The code was subsequently secured with stricter type checks against empty response values.

Environment Variables and Path Evaluation
Flawed path and variable evaluations when loading .env files resulted in empty strings being passed to the OpenAI SDK. This caused false connection errors that were actually rooted in missing authentication parameters.


Key Learnings
API keys must be kept extremely secure and strictly belong in an .env file that is excluded from version control via .gitignore.

Scraping is easy, but extracting clean, reliable data from unstructured sources is the real challenge.

Debugging requires methodology. Systematically isolating and fixing issues step-by-step delivers genuine success when a bug is resolved.

Newsletters are a great format. In the end, however, you also just have to go out into the city analog-style and talk to real people. The best tips for concerts, exhibitions, and parties come naturally through direct conversation.


Repository Structure
newsletter_NY.py: Main script for data aggregation, cleaning, and HTML generation.

debug_api.py: Test script for isolating and verifying individual APIs.

venues.json: Configuration file containing target venues.

index_clean1.html: Sample generated HTML output.

.gitignore: Configuration file to exclude sensitive data.
