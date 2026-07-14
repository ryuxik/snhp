import time
import sys
import os

# Add current directory to path so we can import from snhp module natively
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import snhp

# ANSI Colors
CYAN = '\033[96m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RESET = '\033[0m'
BOLD = '\033[1m'

def type_effect(text, speed=0.005, color=RESET):
    # A bit faster but still snappy
    sys.stdout.write(color)
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(speed)
    sys.stdout.write(RESET + "\n")

def main():
    print(CYAN + BOLD + "=" * 60)
    print("          SNHP NEGOTIATION ENGINE (LIVE TERMINAL)")
    print("=" * 60 + RESET + "\n")
    
    type_effect("Paste the exact email or message from the client:", color=CYAN+BOLD)
    print("  (Press Enter twice to finish typing/pasting)\n")
    
    # We read until an empty line to allow for multiline pasting
    lines = []
    while True:
        try:
            line = input()
            if line.strip() == "":
                break
            lines.append(line)
        except EOFError:
            break
            
    client_email = "\n".join(lines).strip()
    
    if not client_email:
        print("No email provided. Exiting.")
        return

    print("\n" + CYAN + BOLD + "-" * 60 + RESET)
    type_effect("What are your constraints? State them naturally.", color=CYAN+BOLD)
    type_effect("Example: 'I need minimum $100/hr, absolute max 14 days, ideal 7 days'", color=CYAN)
    
    try:
        constraints = input(f"\n{BOLD}You:{RESET} ")
    except EOFError:
        print("\nExiting SNHP...")
        return
        
    print("\n" + CYAN + BOLD + "-" * 60 + RESET)
    type_effect("[Connecting to SNHP Game Theory Engine...]", speed=0.01, color=YELLOW)
    type_effect("[Parsing multidimensional constraints...]", speed=0.01, color=YELLOW)
    print()
    
    # Run exact SNHP logic using the native SDK
    try:
        response = snhp.negotiate(client_email, constraints)
        output = snhp.format_markdown(response)
        print(GREEN + output + RESET + "\n")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error calculating optimal negotiation: {e}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nExiting SNHP...")
