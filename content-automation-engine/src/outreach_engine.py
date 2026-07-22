import logging
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def draft_expert_outreach(name, paper_title):
    """Drafts an email inviting a researcher/expert to the YouTube channel."""
    return f"""
Subject: Interview Invitation: Your work on {paper_title}

Dear Dr. {name},

I recently read your fascinating research on "{paper_title}" and was thoroughly impressed by your findings.

I run a YouTube channel and blog focused on the intersection of Technology and Sanskrit/Ancient Knowledge systems, and I would love to feature your work. Would you be open to a brief 20-minute video interview to discuss your paper? 

Looking forward to hearing from you.

Best regards,
[Your Name]
    """

def draft_newsletter_update():
    """Drafts a weekly newsletter summarizing the latest content."""
    return f"""
Subject: This Week in Sanskrit & AI: New Discoveries!

Hi everyone,

It's been a busy week at the intersection of AI and ancient linguistics. I've just published a new video and blog post breaking down how computational linguistics is revolutionizing our understanding of ancient texts.

Check it out here: [LINK]

As always, reply to this email with your thoughts—I read every single one.

Best,
[Your Name]
    """

def run_outreach():
    logging.info("Running Outreach & CRM Engine...")
    
    outreach_dir = "outreach_drafts"
    os.makedirs(outreach_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Draft Newsletter
    newsletter = draft_newsletter_update()
    with open(os.path.join(outreach_dir, f"{date_str}_newsletter.txt"), "w", encoding="utf-8") as f:
        f.write(newsletter.strip())
    logging.info("Newsletter drafted.")
    
    # 2. Draft Expert Outreach (Mock data representing newly discovered authors)
    experts = [
        {"name": "Amba Kulkarni", "paper": "Computational Parsing of Sanskrit"},
        {"name": "Oliver Hellwig", "paper": "Deep Learning for Sanskrit Tagging"}
    ]
    
    for expert in experts:
        email = draft_expert_outreach(expert["name"], expert["paper"])
        safe_name = expert['name'].replace(" ", "_").lower()
        with open(os.path.join(outreach_dir, f"{date_str}_outreach_{safe_name}.txt"), "w", encoding="utf-8") as f:
            f.write(email.strip())
            
    logging.info(f"Drafted {len(experts)} outreach emails.")

if __name__ == "__main__":
    run_outreach()
