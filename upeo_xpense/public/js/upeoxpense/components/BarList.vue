<script setup>
import { computed } from "vue";
import { money } from "../format.js";

const props = defineProps({
	items: { type: Array, default: () => [] }, // [{label, total, count}]
	currency: { type: String, default: "KES" },
});

const max = computed(() => Math.max(1, ...props.items.map((i) => i.total)));
</script>

<template>
	<div class="ux-barlist">
		<div v-for="(item, i) in items" :key="i" class="ux-bar-row">
			<div class="ux-bar-head">
				<span class="ux-bar-label" :title="item.label">{{ item.label }}</span>
				<span class="ux-bar-value">{{ money(item.total, currency) }}</span>
			</div>
			<div class="ux-bar-track">
				<div class="ux-bar-fill" :style="{ width: `${Math.max(4, (item.total / max) * 100)}%` }"></div>
			</div>
			<span v-if="item.count" class="ux-bar-count">{{ item.count }} receipt{{ item.count === 1 ? "" : "s" }}</span>
		</div>
		<div v-if="!items.length" class="ux-empty-inline">Nothing to show yet.</div>
	</div>
</template>

<style scoped>
.ux-barlist { display: flex; flex-direction: column; gap: 14px; }
.ux-bar-row { display: flex; flex-direction: column; gap: 5px; }
.ux-bar-head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
.ux-bar-label { font-size: 13px; font-weight: 600; color: var(--ux-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ux-bar-value { font-size: 12.5px; font-weight: 700; color: var(--ux-text); white-space: nowrap; }
.ux-bar-track { height: 8px; border-radius: 999px; background: var(--ux-border); overflow: hidden; }
.ux-bar-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #c9a227, #e6c757); }
.ux-bar-count { font-size: 11px; color: var(--ux-text-dim); }
.ux-empty-inline { text-align: center; color: var(--ux-text-dim); font-size: 13px; padding: 8px; }
</style>
