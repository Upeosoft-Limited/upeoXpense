<script setup>
defineProps({
	label: String,
	value: [String, Number],
	sub: String,
	accent: { type: Boolean, default: false },
	icon: String,
});
</script>

<template>
	<div class="ux-kpi" :class="{ accent }">
		<div class="ux-kpi-top">
			<span class="ux-kpi-label">{{ label }}</span>
			<span v-if="icon" class="ux-kpi-icon" v-html="icon"></span>
		</div>
		<div class="ux-kpi-value">{{ value }}</div>
		<div v-if="sub" class="ux-kpi-sub">{{ sub }}</div>
	</div>
</template>

<style scoped>
.ux-kpi {
	background: var(--ux-surface);
	border: 1px solid var(--ux-border);
	border-radius: 16px;
	padding: 18px 20px;
	display: flex;
	flex-direction: column;
	gap: 6px;
	min-height: 108px;
	position: relative;
	overflow: hidden;
	transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.ux-kpi:hover { transform: translateY(-2px); box-shadow: 0 10px 30px rgba(20, 17, 10, 0.08); }
.ux-kpi.accent {
	background: linear-gradient(150deg, #1c1710 0%, #2a2114 100%);
	border-color: rgba(212, 175, 55, 0.35);
}
.ux-kpi.accent .ux-kpi-label { color: rgba(245, 237, 214, 0.7); }
.ux-kpi.accent .ux-kpi-value { color: var(--ux-gold); }
.ux-kpi.accent .ux-kpi-sub { color: rgba(245, 237, 214, 0.55); }
.ux-kpi-top { display: flex; align-items: center; justify-content: space-between; }
.ux-kpi-label {
	font-size: 12px;
	font-weight: 600;
	letter-spacing: 0.4px;
	text-transform: uppercase;
	color: var(--ux-text-dim);
}
.ux-kpi-icon { color: var(--ux-gold); display: inline-flex; }
.ux-kpi-value { font-size: 28px; font-weight: 700; color: var(--ux-text); line-height: 1.1; letter-spacing: -0.5px; }
.ux-kpi-sub { font-size: 12.5px; color: var(--ux-text-dim); }
</style>
