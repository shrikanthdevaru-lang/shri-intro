import logging
from src.discover_trends import get_trending_topics
from src.generate_content import process_topics
from src.outreach_engine import run_outreach
from src.post_to_blogger import post_to_blogger

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    logging.info("Starting Advanced Content Automation & CRM Workflow...")
    
    # 1. Discover Trends
    logging.info("--- PHASE 1: DISCOVERY ---")
    get_trending_topics()
    
    # 2. Generate Content
    logging.info("--- PHASE 2: CONTENT GENERATION ---")
    process_topics()
    
    # 3. CRM & Outreach
    logging.info("--- PHASE 3: CRM & OUTREACH ---")
    run_outreach()
    
    # 4. Publishing
    logging.info("--- PHASE 4: PUBLISHING ---")
    post_to_blogger()
    
    logging.info("Workflow completed successfully. Check the generated_content/ and outreach_drafts/ directories.")

if __name__ == "__main__":
    main()
