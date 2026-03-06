from backend import AGENT, ChatSession, get_bot_reply

def main():
    print("Rina is ready. Type 'exit' to quit.")
    session = ChatSession()

    while True:
        user_input = input("You: ")
        if user_input.lower() == "exit":
            break
        print(f"\n{AGENT}: ", end="", flush=True)
        try:
            get_bot_reply(session, user_input)
        except Exception as e:
            print(f"\n[Error: {e}]")
        print()

if __name__ == "__main__":
    main()
