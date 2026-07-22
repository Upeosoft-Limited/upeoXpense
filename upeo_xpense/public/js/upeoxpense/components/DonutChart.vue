<script setup>
import { computed } from "vue";

const props = defineProps({
	segments: { type: Array, default: () => [] }, // [{label, value, color}]
	caption: { type: String, default: "receipts" },
	emptyText: { type: String, default: "No receipts yet." },
});

const total = computed(() => props.segments.reduce((s, x) => s + x.value, 0));

const arcs = computed(() => {
	const R = 60;
	const C = 2 * Math.PI * R;
	let offset = 0;
	return props.segments
		.filter((s) => s.value > 0)
		.map((s) => {
			const frac = s.value / (total.value || 1);
			const len = frac * C;
			const arc = { ...s, dash: `${len} ${C - len}`, offset: -offset, C, R };
			offset += len;
			return arc;
		});
});
</script>

<template>
	<div class="ux-donut">
		<svg viewBox="0 0 160 160" class="ux-donut-svg">
			<circle cx="80" cy="80" :r="60" fill="none" stroke="var(--ux-border)" stroke-width="18" />
			<circle
				v-for="(a, i) in arcs"
				:key="i"
				cx="80"
				cy="80"
				:r="a.R"
				fill="none"
				:stroke="a.color"
				stroke-width="18"
				:stroke-dasharray="a.dash"
				:stroke-dashoffset="a.offset"
				transform="rotate(-90 80 80)"
				stroke-linecap="butt"
			/>
			<text x="80" y="74" text-anchor="middle" class="ux-donut-num">{{ total }}</text>
			<text x="80" y="92" text-anchor="middle" class="ux-donut-cap">{{ caption }}</text>
		</svg>
		<div class="ux-donut-legend">
			<div v-for="(s, i) in segments.filter((x) => x.value > 0)" :key="i" class="ux-legend-row">
				<span class="ux-legend-dot" :style="{ background: s.color }"></span>
				<span class="ux-legend-label">{{ s.label }}</span>
				<span class="ux-legend-val">{{ s.value }}</span>
			</div>
			<div v-if="!total" class="ux-empty-inline">{{ emptyText }}</div>
		</div>
	</div>
</template>

<style scoped>
.ux-donut { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
.ux-donut-svg { width: 148px; height: 148px; flex-shrink: 0; }
.ux-donut-num { font-size: 30px; font-weight: 700; fill: var(--ux-text); }
.ux-donut-cap { font-size: 11px; fill: var(--ux-text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.ux-donut-legend { display: flex; flex-direction: column; gap: 9px; flex: 1; min-width: 140px; }
.ux-legend-row { display: flex; align-items: center; gap: 9px; }
.ux-legend-dot { width: 10px; height: 10px; border-radius: 3px; flex-shrink: 0; }
.ux-legend-label { font-size: 13px; color: var(--ux-text); flex: 1; }
.ux-legend-val { font-size: 13px; font-weight: 700; color: var(--ux-text); }
.ux-empty-inline { color: var(--ux-text-dim); font-size: 13px; }
</style>
