from cortex import AGENT, ChatSession, stream_bot_reply

def main():
    print("Rina is ready. Type 'exit' to quit.")
    session = ChatSession()

    while True:
        user_input = input("You: ")
        if user_input.lower() == "exit":
            break
        if user_input.lower() == "/reset":
            session.reset()
            print("[Memory cleared. Starting fresh.]")
            continue
        print(f"\n{AGENT}: ", end="", flush=True)
        try:
            for token in stream_bot_reply(session, user_input):
                print(token, end="", flush=True)
        except Exception as e:
            print(f"\n[Error: {e}]")
        print()

if __name__ == "__main__":
    main()
