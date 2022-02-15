
class Message:
    @classmethod
    def entry(cls, tag, coin, entry, quantity, side, sl, rr):
        fund = quantity * entry
        risk = abs(quantity * entry - quantity * sl)
        return (f"📣 {tag}: {side} {quantity} {coin} @ ${round(entry, 5)}\n"
                f"💰 ${round(fund, 2)} (risk: ${round(risk, 2)}, rr: {round(rr, 2)})")

    @classmethod
    def error(cls, tag, message):
        return f"🚫 {tag}: {message}"

    @classmethod
    def target(cls, tag, coin, entry, q_entry, target, q_target, is_long, is_sl=False):
        side = "SELL" if is_long else "BUY"
        initial = q_target * entry
        final = q_target * target
        profit = final - initial
        if not is_long:
            profit = -profit
        if profit > 0:
            s = "🤑"
            msg = f"✅ Profits: ${round(profit, 3)}"
        elif is_sl and q_target < q_entry:
            s = "⚠️"
            msg = "🟠 Stopped at entry after taking profits"
        else:
            s = "‼️"
            msg = f"🛑 Loss: ${round(profit, 3)}"
        return (f"{s} {tag}: {side} {q_target} {coin} @ {round(target, 5)}\n{msg}")

    @classmethod
    def no_margin(cls, symbol: str):
        return f"‼️ No margin available for {symbol}"
