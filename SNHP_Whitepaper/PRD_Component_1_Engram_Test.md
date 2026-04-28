# PRD: Component 1 - The Engram Test (Utility Preference Vector)

## Steve Jobs: The Vision (The "Jobsian Standard")
We are not building a spreadsheet. We are building a bicycle for the mind. If we ask a user to "input a utility vector," they will close the app and throw their phone out the window. It has to be insanely great. The interface must be completely invisible. 

The user should see three beautiful sliders on the screen: Price, Speed, and Quality. As they drag one slider up, they see the other two fluidly adapt. They aren't doing math; they are just telling us what they care about most. It should take a freelancer exactly 8 seconds to communicate their soul's baseline to our engine. If there's friction here, the entire product is garbage.

## Product Requirements
*   **Target Scope:** A 3-variable negotiation (e.g., Price: $10k-$20k, Time: 1-4 weeks, Revisions: 1-5).
*   **User Interface:** Interactive fluid sliders. No raw text-box entry for math terms.
*   **Output:** The UI must seamlessly translate the visual input into a normalized matrix for the backend engine. 

---

## John von Neumann: The Technical Review
*“Steve, your obsession with glass and sliders is charming, but aesthetics are irrelevant if the underlying mathematical normalization fails. If the user’s input violates transitive preferences, your beautiful UI is producing garbage.”*

**Von Neumann's Strict Constraints:**
1.  **Normalization Protocol:** The UI must restrict the user such that the sum of their 'Importance Weights' exactly equals 1.0. If you let them drag every slider to 100%, the equation collapses.
2.  **Utility Function Architecture:** We must enforce a linear additive utility model for the MVP. $U(x) = w_1(Price) + w_2(Time) + w_3(Revisions)$. 
3.  **Boundary Truth:** The system must record the user's Absolute Reservation Value (BATNA). If they drag price below their absolute minimum, the system must trigger a hard mathematical stop. No 'reality distortion.'

## MVP Action Plan
1. Build a React/Vite web interface with dynamic, linked sliders.
2. Build the normalization script that converts slider coordinates [0-100] into a mathematical vector $[w_1, w_2, w_3]$.
3. Run qualitative tests on 5 users: Can they define their business boundaries in < 15 seconds?
