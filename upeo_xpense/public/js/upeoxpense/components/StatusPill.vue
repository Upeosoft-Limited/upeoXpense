<script setup>
import { computed } from "vue";
import { STATUS_TONE } from "../format.js";

const props = defineProps({ status: String, tone: String });
const tone = computed(() => props.tone || STATUS_TONE[props.status] || "muted");
</script>

<template>
	<span class="ux-pill" :class="`is-${tone}`">
		<span class="ux-pill-dot"></span>{{ status }}
	</span>
</template>

<style scoped>
.ux-pill {
	display: inline-flex;
	align-items: center;
	gap: 6px;
	padding: 3px 10px 3px 8px;
	border-radius: 999px;
	font-size: 11.5px;
	font-weight: 600;
	letter-spacing: 0.2px;
	white-space: nowrap;
	border: 1px solid transparent;
}
.ux-pill-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.is-good { color: #2f8f5b; background: rgba(47, 143, 91, 0.12); border-color: rgba(47, 143, 91, 0.25); }
.is-warn { color: #a9791b; background: rgba(212, 175, 55, 0.14); border-color: rgba(212, 175, 55, 0.3); }
.is-bad { color: #b4452f; background: rgba(180, 69, 47, 0.12); border-color: rgba(180, 69, 47, 0.25); }
.is-info { color: #3a6ea5; background: rgba(58, 110, 165, 0.12); border-color: rgba(58, 110, 165, 0.22); }
.is-muted { color: #8a8272; background: rgba(138, 130, 114, 0.12); border-color: rgba(138, 130, 114, 0.22); }
</style>
