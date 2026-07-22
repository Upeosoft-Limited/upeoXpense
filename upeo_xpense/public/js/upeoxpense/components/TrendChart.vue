<script setup>
import { computed } from "vue";
import { monthLabel, compactMoney } from "../format.js";

const props = defineProps({
	data: { type: Array, default: () => [] }, // [{month, total, count}]
	currency: { type: String, default: "KES" },
});

const W = 520;
const H = 180;
const PAD = { t: 16, r: 16, b: 28, l: 16 };

const geom = computed(() => {
	const d = props.data;
	if (!d.length) return { points: "", area: "", dots: [], labels: [] };
	const max = Math.max(...d.map((x) => x.total), 1);
	const innerW = W - PAD.l - PAD.r;
	const innerH = H - PAD.t - PAD.b;
	const step = d.length > 1 ? innerW / (d.length - 1) : 0;
	const dots = d.map((x, i) => {
		const px = PAD.l + step * i;
		const py = PAD.t + innerH - (x.total / max) * innerH;
		return { x: px, y: py, ...x };
	});
	const line = dots.map((p) => `${p.x},${p.y}`).join(" ");
	const area = `${PAD.l},${PAD.t + innerH} ${line} ${PAD.l + step * (d.length - 1)},${PAD.t + innerH}`;
	return { points: line, area, dots };
});
</script>

<template>
	<div class="ux-trend">
		<svg :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="none" class="ux-trend-svg">
			<defs>
				<linearGradient id="uxTrendFill" x1="0" y1="0" x2="0" y2="1">
					<stop offset="0%" stop-color="var(--ux-gold)" stop-opacity="0.28" />
					<stop offset="100%" stop-color="var(--ux-gold)" stop-opacity="0" />
				</linearGradient>
			</defs>
			<polygon v-if="geom.area" :points="geom.area" fill="url(#uxTrendFill)" />
			<polyline
				v-if="geom.points"
				:points="geom.points"
				fill="none"
				stroke="var(--ux-gold)"
				stroke-width="2.5"
				stroke-linejoin="round"
				stroke-linecap="round"
			/>
			<g v-for="(p, i) in geom.dots" :key="i">
				<circle :cx="p.x" :cy="p.y" r="3.5" fill="var(--ux-bg)" stroke="var(--ux-gold)" stroke-width="2" />
			</g>
		</svg>
		<div class="ux-trend-axis">
			<span v-for="(p, i) in data" :key="i" class="ux-trend-tick">
				<b>{{ compactMoney(p.total, currency) }}</b>
				<em>{{ monthLabel(p.month) }}</em>
			</span>
		</div>
		<div v-if="!data.length" class="ux-empty-inline">No dated receipts yet.</div>
	</div>
</template>

<style scoped>
.ux-trend { display: flex; flex-direction: column; }
.ux-trend-svg { width: 100%; height: 180px; display: block; }
.ux-trend-axis { display: flex; justify-content: space-between; padding: 0 4px; }
.ux-trend-tick { display: flex; flex-direction: column; align-items: center; gap: 2px; flex: 1; }
.ux-trend-tick b { font-size: 11px; color: var(--ux-text); font-weight: 700; }
.ux-trend-tick em { font-size: 11px; color: var(--ux-text-dim); font-style: normal; text-transform: uppercase; letter-spacing: 0.4px; }
.ux-empty-inline { text-align: center; color: var(--ux-text-dim); font-size: 13px; padding: 8px; }
</style>
