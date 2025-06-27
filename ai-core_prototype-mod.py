from backend import ChatSession, get_bot_reply

def main():
    print("Rina is ready. Type 'exit' to quit.")
    session = ChatSession()

    while True:
        user_input = input("You: ")
        if user_input.lower() == "exit":
            break
        reply = get_bot_reply(session, user_input)
        print(f"\nRina: {reply}\n")

if __name__ == "__main__":
    main()
