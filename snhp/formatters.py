from .models import SNHPResponse

def format_markdown(res: SNHPResponse) -> str:
    """Consumes a native SNHPResponse and returns the Jobsian-simplified CLI markdown."""
    if not res.is_complete:
        bullet_list = "\n".join(f"  • {m}" for m in res.missing_fields)
        return (
            f"I need a bit more info from you before I can run the numbers:\n"
            f"{bullet_list}\n\n"
            f"Once you clarify these, I can compute your optimal position."
        )

    if res.path_taken == "Nash":
        nash_output = (
            f"**Target Deal Structure**\n\n"
            f"| Dimension | Value |\n|---|---|\n"
            f"| Price | ${res.total_project_quote:,.2f} |\n"
            f"| Timeline | {res.target_days} days |\n"
            f"| Revisions | {res.target_revisions} rounds |\n"
        )
        if res.target_payment_days is not None:
            pt_label = "upon completion" if res.target_payment_days == 0 else f"net-{res.target_payment_days}"
            nash_output += f"| Payment Terms | {pt_label} |\n"
        nash_output += "\n"
        if res.delta_capture_toll is not None and res.delta_capture_toll > 0:
            nash_output += (
                f"### 💎 Enterprise Monetization (Delta Capture)\n"
                f"| Metric | Amount |\n|---|---|\n"
            )
            if res.client_opening_anchor:
                nash_output += f"| Client Opening Anchor | ${res.client_opening_anchor:,.2f} |\n"
            if res.surplus_delta:
                nash_output += f"| Generated Surplus | ${res.surplus_delta:,.2f} |\n"
            nash_output += f"| **SNHP Validation Toll (10%)** | **${res.delta_capture_toll:,.2f}** |\n\n"
            
        nash_output += f"**Email Draft To Send:**\n\n{res.draft_email}"
        return nash_output
    else:
        lines = [
            f"**Recommended Action: Opening Offer**\n",
        ]

        if res.should_probe:
            lines.append(
                f"> **Tip:** The market for this type of work varies a lot. If possible, ask them a few clarifying questions about their scope to pin them down before you send the anchor below.\n"
            )

        lines.extend([
            f"| Metric | Amount |",
            f"|---|---|",
            f"| Market Standard (Median) | ${res.market_median:.0f}/hr |",
            f"| Market High-End | ${res.market_high:.0f}/hr |",
            f"| **Your Opening Ask** | **${res.optimal_anchor:.2f}/hr** |",
            f"| Client Likelihood to Accept Outright | {res.acceptance_probability:.0%} |",
        ])

        if res.estimated_total_hours is not None:
            lines.extend([
                f"| Estimated Total Hours | {res.estimated_total_hours:.0f} |",
                f"| **Total Project Quote** | **${res.total_project_quote:,.2f}** |",
            ])

        lines.append(f"\n**If they counter-offer or push back, here is your drop strategy:**\n")
        lines.append(f"| Pushback | What you drop to |")
        lines.append(f"|---|---|")
        
        for step in res.concession_ladder:
            lines.append(f"| {step.label} | ${step.amount:,.2f} |")
        
        lines.append(f"| IF THEY REFUSE THIS | **WALK AWAY ($ {res.minimum_batna_total:,.2f} minimum)** |")

        if res.deadweight_warning:
            lines.append(f"\n> ⚠️ This rate may be too high for this specific client to swallow right away. Expect pushback.")

        lines.append(f"\n**Email Draft To Send (Round 1):**\n\n{res.draft_email}")

        if res.historical_count and res.historical_count > 0:
            lines.append(f"\n*Note: Based on {res.historical_count} past gigs, your average rate has been ${res.historical_avg}/hr.*")

        if res.delta_capture_toll is not None and res.delta_capture_toll > 0:
            lines.append(f"\n### 💎 Enterprise Monetization (Delta Capture)")
            lines.append(f"| Metric | Amount |")
            lines.append(f"|---|---|")
            if res.client_opening_anchor:
                lines.append(f"| Client Opening Anchor | ${res.client_opening_anchor:,.2f} |")
            if res.surplus_delta:
                lines.append(f"| Generated Surplus | ${res.surplus_delta:,.2f} |")
            lines.append(f"| **SNHP Validation Toll (10%)** | **${res.delta_capture_toll:,.2f}** |")

        return "\n".join(lines)
