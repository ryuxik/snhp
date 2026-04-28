document.addEventListener("DOMContentLoaded", () => {
    const computeBtn = document.getElementById("computeBtn");
    const resetBtn = document.getElementById("resetBtn");
    
    const inputPanel = document.getElementById("inputPanel");
    const magicPanel = document.getElementById("magicPanel");
    const resultPanel = document.getElementById("resultPanel");
    
    const emailText = document.getElementById("emailText");
    const goalsText = document.getElementById("goalsText");
    
    const magicText = document.getElementById("magicText");
    const latticeCanvas = document.getElementById("latticeCanvas");
    const ctx = latticeCanvas.getContext("2d");
    
    let apiKey = null;
    let currentAnimationId = null;

    // Fetch a test key immediately upon loading
    fetch("http://127.0.0.1:8000/generate_key", { method: "POST" })
        .then(res => res.json())
        .then(data => { apiKey = data.key; })
        .catch(err => console.error("Failed to fetch API key. Ensure backend is running.", err));

    computeBtn.addEventListener("click", async () => {
        if (!apiKey) {
            alert("No API Key loaded. Please check backend connection.");
            return;
        }

        // We bypass local validation of input fields for the perfect golden path demo,
        // allowing the user to just hit compute.

        // Switch to magic state
        inputPanel.classList.add("hidden");
        magicPanel.classList.remove("hidden");
        
        // Start animation
        runLatticeAnimation();

        try {
            // Trigger API
            const response = await fetch("http://127.0.0.1:8000/simulate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    api_key: apiKey,
                    email_text: emailText.value || "Test scenario",
                    goals: goalsText.value || "Test constraints"
                })
            });

            if (!response.ok) {
                throw new Error("Simulation failed");
            }

            const data = await response.json();
            
            // Artificial delay to let the animation play out and demonstrate "work"
            setTimeout(() => {
                showResults(data);
            }, 2500);

        } catch (err) {
            console.error(err);
            alert("Failed to compute optimal path. Ensure backend is running at :8000.");
            resetUI();
        }
    });

    resetBtn.addEventListener("click", resetUI);

    function resetUI() {
        resultPanel.classList.add("hidden");
        magicPanel.classList.add("hidden");
        inputPanel.classList.remove("hidden");
        
        emailText.value = "";
        goalsText.value = "";
    }

    function showResults(data) {
        magicPanel.classList.add("hidden");
        resultPanel.classList.remove("hidden");

        const amountSavedEl = document.getElementById("amountSaved");
        const ladderEl = document.getElementById("concessionLadder");

        amountSavedEl.textContent = `$${data.impact_summary.amount_saved_usd.toLocaleString()}`;
        
        ladderEl.innerHTML = "";
        data.concession_ladder.forEach(step => {
            const stepDiv = document.createElement("div");
            stepDiv.className = "ladder-step";
            stepDiv.innerHTML = `
                <div class="step-strategy">${step.step}. ${step.strategy}</div>
                <div class="step-bid">$${step.bid.toLocaleString()}</div>
                <div class="step-rationale">${step.rationale}</div>
            `;
            ladderEl.appendChild(stepDiv);
        });
    }

    function runLatticeAnimation() {
        if (currentAnimationId) {
            cancelAnimationFrame(currentAnimationId);
        }
        const width = latticeCanvas.width;
        const height = latticeCanvas.height;
        ctx.clearRect(0, 0, width, height);

        let progress = 0;

        const phases = [
            "Parsing negotiation surface...",
            "Computing inverse hazard rate...",
            "Locking Nash Equilibrium..."
        ];

        function draw() {
            ctx.clearRect(0, 0, width, height);
            
            // Draw austere background grid
            ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
            ctx.lineWidth = 1;
            for (let i = 0; i < width; i += 40) {
                ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, height); ctx.stroke();
            }
            for (let i = 0; i < height; i += 40) {
                ctx.beginPath(); ctx.moveTo(0, i); ctx.lineTo(width, i); ctx.stroke();
            }

            // Draw fluid curve
            ctx.beginPath();
            ctx.moveTo(0, height);
            
            // A smooth curve to simulate optimal path finding
            const currentX = width * (progress / 100);
            const currentY = height - (height * Math.sin((progress / 100) * (Math.PI / 2)));

            // Draw path taken so far
            ctx.beginPath();
            ctx.moveTo(0, height);
            for(let p = 0; p <= progress; p+=1) {
                let px = width * (p / 100);
                let py = height - (height * Math.sin((p / 100) * (Math.PI / 2)));
                ctx.lineTo(px, py);
            }
            
            ctx.strokeStyle = "#FFD700";
            ctx.lineWidth = 2;
            ctx.shadowBlur = 15;
            ctx.shadowColor = "#FFD700";
            ctx.stroke();

            // The scanning node
            ctx.beginPath();
            ctx.arc(currentX, currentY, 4, 0, Math.PI * 2);
            ctx.fillStyle = "#FFD700";
            ctx.fill();
            
            // Dynamic text update
            if (progress < 33) magicText.textContent = phases[0];
            else if (progress < 66) magicText.textContent = phases[1];
            else magicText.textContent = phases[2];

            if (progress < 100) {
                progress += 0.7; // Tweak for exact feeling of "computational weight"
                currentAnimationId = requestAnimationFrame(draw);
            }
        }

        draw();
    }
});
