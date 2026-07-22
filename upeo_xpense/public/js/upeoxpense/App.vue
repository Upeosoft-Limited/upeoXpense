<script setup>
import { ref, reactive, provide, onMounted, computed } from "vue";
import api from "./api.js";
import Dashboard from "./views/Dashboard.vue";
import Receipts from "./views/Receipts.vue";
import Claims from "./views/Claims.vue";
import Categories from "./views/Categories.vue";
import Settings from "./views/Settings.vue";

const props = defineProps({ boot: { type: Object, default: () => ({}) } });

const identity = reactive({
	full_name: props.boot.full_name || props.boot.user || "",
	user: props.boot.user || "",
	is_manager: false,
	can_manage_settings: false,
	currency: "KES",
	loaded: false,
});

const view = ref("dashboard");
const mobileNav = ref(false);

const NAV = [
	{ key: "dashboard", label: "Overview", icon: "grid" },
	{ key: "receipts", label: "Expenses", icon: "receipt" },
	{ key: "claims", label: "Expense Claims", icon: "check" },
	{ key: "categories", label: "Categories", icon: "tag", managerOnly: true },
	{ key: "settings", label: "Settings", icon: "cog", adminOnly: true },
];

const visibleNav = computed(() =>
	NAV.filter(
		(n) =>
			(!n.managerOnly || identity.is_manager || identity.can_manage_settings) &&
			(!n.adminOnly || identity.can_manage_settings)
	)
);

const current = computed(() => {
	return { dashboard: Dashboard, receipts: Receipts, claims: Claims, categories: Categories, settings: Settings }[view.value];
});

function go(key) {
	view.value = key;
	mobileNav.value = false;
}

// ---- Toasts -------------------------------------------------------------
const toasts = reactive([]);
let toastId = 0;
function toast(message, tone = "info") {
	const id = ++toastId;
	toasts.push({ id, message, tone });
	setTimeout(() => {
		const i = toasts.findIndex((t) => t.id === id);
		if (i !== -1) toasts.splice(i, 1);
	}, 4200);
}
provide("toast", toast);
provide("identity", identity);

function initials(name) {
	return (name || "?")
		.split(" ")
		.map((p) => p[0])
		.filter(Boolean)
		.slice(0, 2)
		.join("")
		.toUpperCase();
}

onMounted(async () => {
	try {
		const b = await api.get("bootstrap");
		Object.assign(identity, b, { loaded: true });
	} catch (e) {
		identity.loaded = true;
		toast(e.message || "Could not load your profile.", "bad");
	}
});

const ICONS = {
	grid: '<path d="M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z"/>',
	receipt: '<path d="M4 2v20l2-1.5L8 22l2-1.5L12 22l2-1.5L16 22l2-1.5L20 22V2l-2 1.5L16 2l-2 1.5L12 2l-2 1.5L8 2 6 3.5 4 2z"/><path d="M8 7h8M8 11h8M8 15h5"/>',
	check: '<path d="M9 12l2 2 4-4"/><rect x="3" y="4" width="18" height="16" rx="2"/>',
	tag: '<path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/>',
	cog: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
};
</script>

<template>
	<div class="ux-app">
		<!-- Sidebar -->
		<aside class="ux-side" :class="{ open: mobileNav }">
			<div class="ux-brand">
				<div class="ux-logo">U</div>
				<div class="ux-brand-text">
					<span class="ux-brand-name">UpeoXpense</span>
					<span class="ux-brand-tag">Receipt Intelligence</span>
				</div>
			</div>
			<nav class="ux-nav">
				<button
					v-for="item in visibleNav"
					:key="item.key"
					class="ux-nav-item"
					:class="{ active: view === item.key }"
					@click="go(item.key)"
				>
					<svg class="ux-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" v-html="ICONS[item.icon]"></svg>
					<span>{{ item.label }}</span>
				</button>
			</nav>
			<div class="ux-side-foot">
				<a class="ux-desk-link" href="/app/upeoxpense" title="Open the Frappe desk">
					<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M7 17 17 7M9 7h8v8" stroke-linecap="round" stroke-linejoin="round"/></svg>
					Admin desk
				</a>
			</div>
		</aside>

		<!-- Main -->
		<div class="ux-main">
			<header class="ux-top">
				<button class="ux-burger" @click="mobileNav = !mobileNav" aria-label="Menu">
					<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M3 12h18M3 18h18" stroke-linecap="round"/></svg>
				</button>
				<div class="ux-top-title">
					<h1>{{ visibleNav.find((n) => n.key === view)?.label }}</h1>
				</div>
				<div class="ux-user">
					<div class="ux-user-meta">
						<span class="ux-user-name">{{ identity.full_name }}</span>
						<span class="ux-user-role">{{ identity.is_manager ? "Manager" : "Member" }}</span>
					</div>
					<div class="ux-avatar">{{ initials(identity.full_name) }}</div>
				</div>
			</header>

			<main class="ux-content">
				<component :is="current" />
			</main>
		</div>

		<!-- Toasts -->
		<div class="ux-toasts">
			<transition-group name="ux-toast">
				<div v-for="t in toasts" :key="t.id" class="ux-toast" :class="`is-${t.tone}`">
					{{ t.message }}
				</div>
			</transition-group>
		</div>
	</div>
</template>

<style>
/* ---- Golden design system (global) --------------------------------- */
:root {
	--ux-gold: #c9a227;
	--ux-gold-soft: #e6c757;
	--ux-ink: #14110a;
	--ux-bg: #faf7ef;
	--ux-surface: #ffffff;
	--ux-surface-2: #f4efe2;
	--ux-border: #e7e0cd;
	--ux-text: #221d12;
	--ux-text-dim: #8a8272;
	--ux-shadow: 0 1px 3px rgba(20, 17, 10, 0.06);
	--ux-radius: 16px;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
	font-family: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
	background: var(--ux-bg);
	color: var(--ux-text);
	-webkit-font-smoothing: antialiased;
}
button { font-family: inherit; }

/* Shared primitives used across views */
.ux-card {
	background: var(--ux-surface);
	border: 1px solid var(--ux-border);
	border-radius: var(--ux-radius);
	box-shadow: var(--ux-shadow);
}
.ux-section-title { font-size: 14px; font-weight: 700; color: var(--ux-text); margin: 0; letter-spacing: 0.2px; }
.ux-section-sub { font-size: 12.5px; color: var(--ux-text-dim); margin: 2px 0 0; }
.ux-btn {
	display: inline-flex; align-items: center; justify-content: center; gap: 7px;
	border-radius: 10px; padding: 9px 16px; font-size: 13.5px; font-weight: 600;
	border: 1px solid var(--ux-border); background: var(--ux-surface); color: var(--ux-text);
	cursor: pointer; transition: all 0.15s ease;
}
.ux-btn:hover { border-color: var(--ux-gold); }
.ux-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.ux-btn-primary { background: linear-gradient(150deg, #14110a, #2a2114); color: var(--ux-gold-soft); border-color: transparent; }
.ux-btn-primary:hover { background: linear-gradient(150deg, #1c1710, #362a17); border-color: var(--ux-gold); }
.ux-btn-gold { background: linear-gradient(150deg, #c9a227, #e6c757); color: #221d12; border-color: transparent; }
.ux-btn-gold:hover { filter: brightness(1.04); }
.ux-btn-danger { color: #b4452f; border-color: rgba(180, 69, 47, 0.35); }
.ux-btn-danger:hover { background: rgba(180, 69, 47, 0.08); border-color: #b4452f; }
.ux-input, .ux-select {
	width: 100%; padding: 10px 12px; border-radius: 10px; font-size: 13.5px;
	border: 1px solid var(--ux-border); background: var(--ux-surface); color: var(--ux-text);
}
.ux-input:focus, .ux-select:focus { outline: none; border-color: var(--ux-gold); box-shadow: 0 0 0 3px rgba(201, 162, 39, 0.15); }
.ux-skeleton { background: linear-gradient(90deg, var(--ux-surface-2) 25%, #ece5d4 37%, var(--ux-surface-2) 63%); background-size: 400% 100%; animation: ux-shimmer 1.4s ease infinite; border-radius: 8px; }
@keyframes ux-shimmer { 0% { background-position: 100% 0; } 100% { background-position: -100% 0; } }
</style>

<style scoped>
.ux-app { display: flex; min-height: 100vh; background: var(--ux-bg); }

/* Sidebar */
.ux-side {
	width: 244px;
	background: linear-gradient(180deg, #14110a 0%, #1c1710 100%);
	color: #f5edd6;
	display: flex;
	flex-direction: column;
	padding: 22px 16px;
	position: sticky;
	top: 0;
	height: 100vh;
	flex-shrink: 0;
}
.ux-brand { display: flex; align-items: center; gap: 12px; padding: 4px 6px 22px; }
.ux-logo {
	width: 40px; height: 40px; border-radius: 12px;
	background: linear-gradient(150deg, #c9a227, #e6c757);
	color: #14110a; font-weight: 800; font-size: 20px;
	display: flex; align-items: center; justify-content: center;
	box-shadow: 0 4px 14px rgba(201, 162, 39, 0.35);
}
.ux-brand-text { display: flex; flex-direction: column; }
.ux-brand-name { font-size: 15.5px; font-weight: 700; letter-spacing: 0.2px; }
.ux-brand-tag { font-size: 11px; color: rgba(245, 237, 214, 0.5); letter-spacing: 0.3px; }
.ux-nav { display: flex; flex-direction: column; gap: 4px; margin-top: 6px; }
.ux-nav-item {
	display: flex; align-items: center; gap: 12px;
	padding: 11px 13px; border-radius: 11px;
	background: transparent; border: none; color: rgba(245, 237, 214, 0.72);
	font-size: 14px; font-weight: 500; cursor: pointer; text-align: left;
	transition: all 0.15s ease;
}
.ux-nav-item:hover { background: rgba(255, 255, 255, 0.05); color: #f5edd6; }
.ux-nav-item.active { background: rgba(201, 162, 39, 0.16); color: var(--ux-gold-soft); font-weight: 600; }
.ux-nav-item.active .ux-nav-icon { color: var(--ux-gold-soft); }
.ux-nav-icon { width: 19px; height: 19px; flex-shrink: 0; color: rgba(245, 237, 214, 0.6); }
.ux-side-foot { margin-top: auto; padding-top: 16px; border-top: 1px solid rgba(255, 255, 255, 0.08); }
.ux-desk-link { display: inline-flex; align-items: center; gap: 7px; font-size: 12.5px; color: rgba(245, 237, 214, 0.55); text-decoration: none; padding: 8px 6px; }
.ux-desk-link:hover { color: var(--ux-gold-soft); }

/* Main column */
.ux-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.ux-top {
	display: flex; align-items: center; gap: 16px;
	padding: 16px 30px;
	background: rgba(250, 247, 239, 0.85);
	backdrop-filter: blur(8px);
	border-bottom: 1px solid var(--ux-border);
	position: sticky; top: 0; z-index: 20;
}
.ux-top-title h1 { margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -0.3px; }
.ux-burger { display: none; background: none; border: none; color: var(--ux-text); cursor: pointer; padding: 4px; }
.ux-user { margin-left: auto; display: flex; align-items: center; gap: 12px; }
.ux-user-meta { display: flex; flex-direction: column; align-items: flex-end; line-height: 1.25; }
.ux-user-name { font-size: 13.5px; font-weight: 600; color: var(--ux-text); }
.ux-user-role { font-size: 11.5px; color: var(--ux-text-dim); }
.ux-avatar {
	width: 38px; height: 38px; border-radius: 11px;
	background: linear-gradient(150deg, #2a2114, #14110a);
	color: var(--ux-gold-soft); font-weight: 700; font-size: 13.5px;
	display: flex; align-items: center; justify-content: center;
	border: 1px solid rgba(201, 162, 39, 0.4);
}
.ux-content { flex: 1; padding: 28px 30px 56px; max-width: 1240px; width: 100%; margin: 0 auto; }

/* Toasts */
.ux-toasts { position: fixed; bottom: 24px; right: 24px; display: flex; flex-direction: column; gap: 10px; z-index: 90; }
.ux-toast {
	padding: 12px 18px; border-radius: 11px; font-size: 13.5px; font-weight: 500;
	color: #fff; box-shadow: 0 10px 30px rgba(20, 17, 10, 0.2); max-width: 340px;
}
.ux-toast.is-info { background: #2a2114; }
.ux-toast.is-good { background: #2f8f5b; }
.ux-toast.is-bad { background: #b4452f; }
.ux-toast-enter-active, .ux-toast-leave-active { transition: all 0.3s ease; }
.ux-toast-enter-from, .ux-toast-leave-to { opacity: 0; transform: translateX(30px); }

@media (max-width: 860px) {
	.ux-side {
		position: fixed; z-index: 70; left: 0; top: 0;
		transform: translateX(-100%); transition: transform 0.25s ease;
	}
	.ux-side.open { transform: translateX(0); }
	.ux-burger { display: inline-flex; }
	.ux-content { padding: 20px 16px 48px; }
	.ux-top { padding: 14px 16px; }
}
</style>
