// Display helpers shared across views.

export function money(amount, currency) {
	const n = Number(amount || 0);
	const cur = currency || "KES";
	const formatted = n.toLocaleString("en-KE", {
		minimumFractionDigits: 2,
		maximumFractionDigits: 2,
	});
	return `${cur} ${formatted}`;
}

export function compactMoney(amount, currency) {
	const n = Number(amount || 0);
	const cur = currency || "KES";
	if (Math.abs(n) >= 1_000_000) return `${cur} ${(n / 1_000_000).toFixed(1)}M`;
	if (Math.abs(n) >= 1_000) return `${cur} ${(n / 1_000).toFixed(1)}K`;
	return `${cur} ${n.toFixed(0)}`;
}

export function shortDate(value) {
	if (!value) return "-";
	const d = new Date(value);
	if (isNaN(d)) return String(value);
	return d.toLocaleDateString("en-KE", { day: "2-digit", month: "short", year: "numeric" });
}

export function fromNow(value) {
	if (!value) return "";
	const d = new Date(value.replace ? value.replace(" ", "T") : value);
	if (isNaN(d)) return "";
	const secs = Math.floor((Date.now() - d.getTime()) / 1000);
	if (secs < 60) return "just now";
	if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
	if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
	if (secs < 604800) return `${Math.floor(secs / 86400)}d ago`;
	return shortDate(value);
}

export function monthLabel(ym) {
	// ym is "YYYY-MM"
	if (!ym) return "";
	const [y, m] = ym.split("-");
	const d = new Date(Number(y), Number(m) - 1, 1);
	return d.toLocaleDateString("en-KE", { month: "short" });
}

export function confidenceBand(c) {
	const v = Number(c || 0);
	if (v >= 0.85) return { label: "High", tone: "good" };
	if (v >= 0.7) return { label: "Fair", tone: "warn" };
	if (v > 0) return { label: "Low", tone: "bad" };
	return { label: "-", tone: "muted" };
}

export const STATUS_TONE = {
	Queued: "muted",
	Extracting: "info",
	"Awaiting Approval": "warn",
	Approved: "good",
	Reimbursed: "info",
	Rejected: "bad",
	Duplicate: "muted",
	Failed: "bad",
	Draft: "warn",
};
