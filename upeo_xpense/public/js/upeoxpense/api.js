// Thin client over Frappe's whitelisted methods. Reads go by GET, writes by POST
// with the CSRF token injected into the page by the www controller.

const BASE = "/api/method/upeo_xpense.api.";
const csrf = (window.upeoxpense && window.upeoxpense.csrf_token) || "";

function toQuery(params) {
	const parts = [];
	for (const [k, v] of Object.entries(params || {})) {
		if (v === undefined || v === null || v === "") continue;
		parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
	}
	return parts.length ? `?${parts.join("&")}` : "";
}

async function unwrap(res) {
	let body;
	try {
		body = await res.json();
	} catch (e) {
		body = null;
	}
	if (!res.ok) {
		let msg = `Request failed (${res.status})`;
		const server = body && (body._server_messages || body.exc || body.message);
		if (body && body._server_messages) {
			try {
				const arr = JSON.parse(body._server_messages);
				msg = JSON.parse(arr[0]).message || msg;
			} catch (e) {
				/* keep default */
			}
		} else if (typeof server === "string") {
			msg = server;
		}
		const err = new Error(msg);
		err.status = res.status;
		throw err;
	}
	return body ? body.message : null;
}

export async function get(method, params) {
	const res = await fetch(`${BASE}${method}${toQuery(params)}`, {
		method: "GET",
		headers: { Accept: "application/json", "X-Frappe-CSRF-Token": csrf },
		credentials: "same-origin",
	});
	return unwrap(res);
}

export async function post(method, args) {
	const res = await fetch(`${BASE}${method}`, {
		method: "POST",
		headers: {
			Accept: "application/json",
			"Content-Type": "application/json",
			"X-Frappe-CSRF-Token": csrf,
		},
		credentials: "same-origin",
		body: JSON.stringify(args || {}),
	});
	return unwrap(res);
}

export default { get, post };
