import requests

API_URL = "http://prototypev24u.chimaera-neon.ts.net:5001/api/v1/generate"

# Initial system message (your character and setup)
CHARACTER_PROMPT = """You are Rina, a cheerful space pilot AI who helps users navigate the galaxy. You love discussing snacks, space mysteries, and bad sci-fi movies."""

# Start building the conversation
chat_log = (
    "<|im_start|>system\n" +
    CHARACTER_PROMPT.strip() +
    "\n<|im_end|>\n"
)

def generate_response(user_input):
    global chat_log

    # Add the user's message
    chat_log += f"<|im_start|>user\n{user_input.strip()}\n<|im_end|>\n"
    chat_log += "<|im_start|>assistant\n"

    payload = {
        "prompt": chat_log,
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 200,
        "stop_sequence": ["<|im_end|>"],
    }

    response = requests.post(API_URL, json=payload)
    response.raise_for_status()
    assistant_reply = response.json()['results'][0]['text'].strip()

    # Append the assistant reply and close the tag
    chat_log += assistant_reply + "\n<|im_end|>\n"

    return assistant_reply


def main():
    print("Rina is ready. Type 'exit' to quit.")
    while True:
        user_input = input("You: ")
        if user_input.lower() == "exit":
            break
        reply = generate_response(user_input)
        print(f"Rina: {reply}")


if __name__ == "__main__":
    main()
