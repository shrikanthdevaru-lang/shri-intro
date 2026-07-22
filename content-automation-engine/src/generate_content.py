import os
import json
import logging
from datetime import datetime

try:
    import google.generativeai as genai
except ImportError:
    genai = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def configure_ai():
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key and genai:
        genai.configure(api_key=api_key)
        return True
    return False

def generate_multi_format_content(topic):
    """
    Generates a blog post, YouTube script, and social media drafts for a given topic.
    Uses Gemini if configured, otherwise falls back to a mock template.
    """
    title = topic['title']
    context = topic['context']
    
    logging.info(f"Generating content for topic: {title}")
    
    if configure_ai():
        try:
            model = genai.GenerativeModel('gemini-1.5-pro')
            
            prompt = f"""
            Act as an expert content creator specializing in {topic['domain']}.
            Topic: {title}
            Context: {context}
            
            Please generate a JSON object with three fields:
            1. "blog_post": A highly engaging, SEO-optimized blog post in Markdown format. Include an introduction, body paragraphs, and a conclusion.
            2. "youtube_script": A structured YouTube video script including Hook, Intro, Main Points, and Outro.
            3. "social_media": 3 short social media posts (LinkedIn, Twitter) promoting this content.
            
            Respond ONLY with the JSON object.
            """
            response = model.generate_content(prompt)
            # Basic JSON extraction (assuming the model follows instructions)
            content_json = response.text.strip()
            if content_json.startswith("```json"):
                content_json = content_json[7:-3]
            return json.loads(content_json)
        except Exception as e:
            logging.error(f"Error calling Gemini API: {e}. Falling back to mock generator.")
    
    # Mock fallback
    logging.warning("Gemini API not configured or failed. Using mock content generator.")
    return {
        "blog_post": f"# {title}\n\n*Drafted by AI Automation*\n\nThis is a placeholder blog post about {context}. In a production environment, this text would be generated dynamically using the Gemini API.",
        "youtube_script": f"[HOOK] Did you know that {title}?\n[INTRO] Welcome back to the channel! Today we're exploring {context}.\n[OUTRO] Subscribe for more!",
        "social_media": f"Excited to share my latest thoughts on {title}! Check out the blog post. #{topic['domain'].replace(' ', '').replace('&', '')}"
    }

def process_topics():
    try:
        with open("discovered_topics.json", "r", encoding="utf-8") as f:
            topics = json.load(f)
    except FileNotFoundError:
        logging.error("No discovered_topics.json found. Run discover_trends.py first.")
        return

    output_dir = "generated_content"
    os.makedirs(output_dir, exist_ok=True)
    
    for i, topic in enumerate(topics):
        content = generate_multi_format_content(topic)
        date_str = datetime.now().strftime("%Y-%m-%d")
        safe_title = topic['title'].replace(" ", "_").replace("'", "").replace("/", "-")[:30].lower()
        
        # Save Blog Post
        with open(os.path.join(output_dir, f"{date_str}_{safe_title}_blog.md"), "w", encoding="utf-8") as f:
            f.write(content["blog_post"])
            
        # Save YouTube Script
        with open(os.path.join(output_dir, f"{date_str}_{safe_title}_yt.txt"), "w", encoding="utf-8") as f:
            f.write(content["youtube_script"])
            
        # Save Social Media
        with open(os.path.join(output_dir, f"{date_str}_{safe_title}_social.txt"), "w", encoding="utf-8") as f:
            f.write(content["social_media"])
            
        logging.info(f"Successfully saved content cluster for: {topic['title']}")

if __name__ == "__main__":
    process_topics()
