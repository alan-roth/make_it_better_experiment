import csv
import logging
import os
import time
from datetime import datetime
import openai
import textstat
from sklearn.feature_extraction.text import CountVectorizer
from textblob import TextBlob
from textdistance import levenshtein
from tqdm import tqdm
from config import OPENAI_API_KEY

# Setting up OpenAI API key
openai.api_key = OPENAI_API_KEY

# Ensure log directory exists
log_dir = 'log'
os.makedirs(log_dir, exist_ok=True)

# Function to calculate the total word count of a conversation
def get_total_word_count(conversation):
    return sum(len(msg['content'].split()) for msg in conversation)

def send_prompt(messages, retries=3):
    for attempt in range(retries):
        try:
            client = openai.OpenAI(api_key=openai.api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=16000,  # Adjust the max_tokens as needed
                temperature=0.7
            )
            # Extract token usage
            tokens_used = response.usage.total_tokens
            content = response.choices[0].message.content
            return content, tokens_used
        except Exception as e:
            logging.error(f"Error sending prompt (attempt {attempt + 1}/{retries}): {e}")
            time.sleep(1)
    logging.error("Failed to send prompt after multiple retries")
    return None, None

def log_conversation(last_user_message, last_assistant_message, log_file=os.path.join(log_dir, 'conversation.csv')):
    try:
        with open(log_file, 'a', newline='') as f:
            writer = csv.writer(f)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow([timestamp, 'user', last_user_message])
            writer.writerow([timestamp, 'assistant', last_assistant_message])
        logging.info("Conversation logged successfully.")
    except Exception as e:
        logging.error(f"Error logging conversation: {e}")

def analyze_changes(previous_text, current_text, csv_file=os.path.join(log_dir, 'analysis.csv')):
    fieldnames = ['Edit Distance', 'Word Count', 'Unique Word Count', 'Sentiment', 'Readability', 'Top N-Grams']
    analysis_result = {}

    try:
        edit_dist = levenshtein.distance(previous_text, current_text)
        word_count = len(current_text.split())
        unique_word_count = len(set(current_text.split()))
        sentiment = TextBlob(current_text).sentiment
        readability_score = textstat.flesch_kincaid_grade(current_text)

        vectorizer = CountVectorizer(ngram_range=(2, 3))
        ngrams = vectorizer.fit_transform([current_text])
        ngrams_counts = ngrams.sum(axis=0).tolist()[0]
        top_ngrams = sorted([(ngram, ngrams_counts[idx]) for ngram, idx in vectorizer.vocabulary_.items()], key=lambda x: -x[1])[:10]

        analysis_result = {
            'Edit Distance': edit_dist,
            'Word Count': word_count,
            'Unique Word Count': unique_word_count,
            'Sentiment': sentiment,
            'Readability': readability_score,
            'Top N-Grams': top_ngrams
        }

        logging.info("Analysis for one iteration completed.")
    except Exception as e:
        logging.error(f"Error analyzing changes: {e}")

    try:
        with open(csv_file, 'a', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if os.stat(csv_file).st_size == 0:
                writer.writeheader()  # Write header only if file is empty
            writer.writerow(analysis_result)
        logging.info("Analysis results saved successfully.")
    except Exception as e:
        logging.error(f"Error writing to CSV file: {e}")

def main():
    initial_prompt = "Write Hello World in Python."
    N = 10  # Define the number of conversation turns
    conversation = [{"role": "system", "content": "You are a helpful AI assistant and an expert AI programming assistant with extensive knowledge in various programming languages, software development best practices, and modern coding patterns. You provide accurate and detailed code snippets, explanations, and debugging advice. Offer iterative improvements and explain the changes made. When providing responses, please ensure they are ethical, unbiased, and factually accurate. Use a clear and concise tone suitable for professional software development contexts. Generate outputs in a structured format"},
                    {"role": "user", "content": initial_prompt}]

    response, tokens_used = send_prompt(conversation)
    if response:
        conversation.append({"role": "assistant", "content": response})
        logging.info(f"Initial response token usage: {tokens_used}")

        # Log initial conversation
        log_conversation(initial_prompt, response)

        # Create a tqdm progress bar for iterations
        with tqdm(total=N, desc="Processing iterations", unit="iteration") as pbar:
            for i in range(N):
                # Ensure the conversation total word count is less than 95,000 words (estimate of context window size)
                while get_total_word_count(conversation) > 95000:
                    # Remove the oldest user-assistant pair (excluding the system message)
                    conversation.pop(2)
                    conversation.pop(2)

                last_user_message = "Thank you, but make it better."
                conversation.append({"role": "user", "content": last_user_message})
                response, tokens_used = send_prompt(conversation)
                if response:
                    last_assistant_message = response
                    conversation.append({"role": "assistant", "content": response})
                    # Update progress bar description with token usage
                    pbar.set_postfix_str(f"Tokens used: {tokens_used}")
                    pbar.update(1)
                    logging.info(f"Iteration {i + 1} completed. Token usage: {tokens_used}")

                    # Log conversation after each iteration
                    log_conversation(last_user_message, last_assistant_message)

                    # Analyze changes only for the last two assistant responses
                    assistant_responses = [msg['content'] for msg in conversation if msg['role'] == 'assistant']
                    if len(assistant_responses) >= 2:
                        analyze_changes(assistant_responses[-2], assistant_responses[-1])
                else:
                    logging.error("Failed to get a response after retries")
                    break

if __name__ == "__main__":
    logging.basicConfig(filename=os.path.join(log_dir, 'error.log'), level=logging.INFO,
                        format='%(asctime)s %(levelname)s:%(message)s')
    main()
