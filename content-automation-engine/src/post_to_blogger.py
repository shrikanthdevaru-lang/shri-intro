import os
import glob
import logging
import markdown
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/blogger']

def authenticate_blogger():
    """Shows basic usage of the Blogger API.
    Prints the names of the blogs the user has access to.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logging.error(f"Error refreshing token: {e}. Re-authenticating...")
                creds = None
                
        if not creds:
            if not os.path.exists('client_secrets.json'):
                logging.warning("client_secrets.json not found! Cannot authenticate with Blogger.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secrets.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    service = build('blogger', 'v3', credentials=creds)
    return service

def post_to_blogger():
    logging.info("Starting Blogger Publishing Engine...")
    service = authenticate_blogger()
    
    if not service:
        logging.error("Failed to authenticate with Blogger. Skipping publishing phase.")
        return
        
    try:
        # First, get the Blog ID
        users_blogs = service.blogs().listByUser(userId='self').execute()
        if not users_blogs.get('items'):
            logging.error("No blogs found for this user.")
            return
            
        # Select the first blog (you can hardcode the BLOG_ID here if needed)
        blog_id = users_blogs['items'][0]['id']
        logging.info(f"Targeting Blog: {users_blogs['items'][0]['name']} (ID: {blog_id})")
        
        # Find generated markdown files
        blog_files = glob.glob("generated_content/*_blog.md")
        
        for file_path in blog_files:
            logging.info(f"Preparing to publish: {file_path}")
            with open(file_path, "r", encoding="utf-8") as f:
                md_content = f.read()
                
            # Extract a basic title from the filename or the first line
            title = os.path.basename(file_path).replace("_blog.md", "").replace("_", " ").title()
            first_line = md_content.split('\n')[0]
            if first_line.startswith('# '):
                title = first_line.replace('# ', '')
                
            # Convert Markdown to HTML
            html_content = markdown.markdown(md_content)
            
            body = {
                "kind": "blogger#post",
                "title": title,
                "content": html_content
            }
            
            # Insert the post
            posts = service.posts()
            request = posts.insert(blogId=blog_id, body=body, isDraft=False)
            response = request.execute()
            logging.info(f"Successfully published! Post URL: {response['url']}")
            
            # Optional: Move the file to a 'published' folder to avoid duplicate posting
            # os.rename(file_path, file_path.replace("generated_content", "published_content"))
            
    except Exception as e:
        logging.error(f"An error occurred while publishing: {e}")

if __name__ == '__main__':
    post_to_blogger()
