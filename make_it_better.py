import csv
import logging
import os
import time
from datetime import datetime
import openai
from tqdm import tqdm
import tiktoken  # Importing the tiktoken package

from config import OPENAI_API_KEY

# Setting up OpenAI API key
openai.api_key = OPENAI_API_KEY

# Ensure log directory exists
log_dir = 'log'
os.makedirs(log_dir, exist_ok=True)

# Initialize tiktoken tokenizer for GPT-4 models
tokenizer = tiktoken.get_encoding("cl100k_base")


# Function to calculate total token count of a conversation
def get_total_token_count(conversation):
    return sum(len(tokenizer.encode(msg['content'])) for msg in conversation)


def send_prompt(conversation, retries=3):
    max_context_tokens = 128000  # The context window limit for the model
    max_tokens_allowed = 16000  # Maximum tokens allowed for the response

    for attempt in range(retries):
        try:
            # Preemptively estimate the total tokens
            total_tokens_estimate = get_total_token_count(conversation)+1000

            # Preemptively reduce the conversation length if needed
            while total_tokens_estimate + max_tokens_allowed > max_context_tokens:
                if len(conversation) > 2:
                    # Remove the oldest user-assistant pair (excluding the system message)
                    conversation.pop(2)
                    conversation.pop(2)
                    total_tokens_estimate = get_total_token_count(conversation)
                else:
                    logging.error("Unable to shorten conversation further during estimation.")
                    break  # Break if the conversation is too short to pop more messages

            # Now send the prompt
            client = openai.OpenAI(api_key=openai.api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=conversation,
                max_tokens=max_tokens_allowed,
                temperature=0.7
            )
            # Extract token usage
            tokens_used = response.usage.total_tokens
            content = response.choices[0].message.content
            return content, tokens_used, conversation  # Return the modified conversation
        except openai.BadRequestError as e:
            # Handle specific token-related errors
            logging.error(f"Token limit exceeded error (attempt {attempt + 1}/{retries}): {e}")

            # Pop the second message (excluding the system message) in case of error
            if len(conversation) > 2:
                conversation.pop(2)
                conversation.pop(2)
            else:
                logging.error("Unable to shorten conversation further after error.")
                break  # If the conversation is too short to pop, break the loop

            time.sleep(1)
        except Exception as e:
            logging.error(f"Error sending prompt (attempt {attempt + 1}/{retries}): {e}")
            time.sleep(1)
    logging.error("Failed to send prompt after multiple retries")
    return None, None, conversation


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


def main():
    initial_prompt = "Write Hello World in Python."
    N = 100  # Define the number of conversation turns
    conversation = [
        {"role": "system",
         "content": "You are a helpful AI assistant and an expert AI programming assistant with extensive knowledge in various programming languages, software development best practices, and modern coding patterns. You provide accurate and detailed code snippets, explanations, and debugging advice. Offer iterative improvements and explain the changes made. When providing responses, please ensure they are ethical, unbiased, and factually accurate. Use a clear and concise tone suitable for professional software development contexts. Generate outputs in a structured format"},
        {"role": "user", "content": initial_prompt}
    ]

    response, tokens_used, conversation = send_prompt(conversation)
    if response:
        conversation.append({"role": "assistant", "content": response})
        logging.info(f"Initial response token usage: {tokens_used}")

        # Log initial conversation
        log_conversation(initial_prompt, response)

        # Create a tqdm progress bar for iterations
        assistant_responses = [response]  # Start with the initial response
        with tqdm(total=N, desc="Processing iterations", unit="iteration") as pbar:
            for i in range(N):

                last_user_message = "Thank you, but make it better. Your intended audience consists of beginner programmers."
                conversation.append({"role": "user", "content": last_user_message})
                response, tokens_used, conversation = send_prompt(conversation)

                if response:
                    last_assistant_message = response
                    conversation.append({"role": "assistant", "content": response})
                    assistant_responses.append(response)
                    # Update progress bar description with token usage
                    pbar.set_postfix_str(f"Tokens used: {tokens_used}")
                    pbar.update(1)
                    logging.info(f"Iteration {i + 1} completed. Token usage: {tokens_used}")

                    # Log conversation after each iteration
                    log_conversation(last_user_message, last_assistant_message)

                else:
                    logging.error("Failed to get a response after retries")
                    break



if __name__ == "__main__":
    logging.basicConfig(filename=os.path.join(log_dir, 'error.log'), level=logging.INFO,
                        format='%(asctime)s %(levelname)s:%(message)s')
    main()
