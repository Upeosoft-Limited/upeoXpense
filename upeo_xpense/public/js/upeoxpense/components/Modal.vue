<script setup>
defineProps({
	open: Boolean,
	title: String,
	subtitle: String,
	confirmLabel: { type: String, default: "Confirm" },
	confirmTone: { type: String, default: "primary" }, // primary | gold | danger
	busy: { type: Boolean, default: false },
	icon: { type: String, default: "check" },
});
const emit = defineEmits(["close", "confirm"]);

const ICONS = {
	check: '<path d="M20 6 9 17l-5-5" stroke-linecap="round" stroke-linejoin="round"/>',
	x: '<path d="M18 6 6 18M6 6l12 12" stroke-linecap="round"/>',
};
</script>

<template>
	<transition name="ux-modal">
		<div v-if="open" class="ux-modal-scrim" @click.self="!busy && emit('close')">
			<div class="ux-modal" :class="`tone-${confirmTone}`" role="dialog" aria-modal="true">
				<div class="ux-modal-head">
					<div class="ux-modal-icon">
						<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" v-html="ICONS[icon] || ICONS.check"></svg>
					</div>
					<div>
						<h3 class="ux-modal-title">{{ title }}</h3>
						<p v-if="subtitle" class="ux-modal-sub">{{ subtitle }}</p>
					</div>
				</div>

				<div class="ux-modal-body">
					<slot />
				</div>

				<div class="ux-modal-foot">
					<button class="ux-btn" :disabled="busy" @click="emit('close')">Cancel</button>
					<button
						class="ux-btn"
						:class="{ 'ux-btn-primary': confirmTone === 'primary', 'ux-btn-gold': confirmTone === 'gold', 'ux-btn-danger': confirmTone === 'danger' }"
						:disabled="busy"
						@click="emit('confirm')"
					>
						<span v-if="busy" class="ux-modal-spin"></span>
						{{ busy ? "Working..." : confirmLabel }}
					</button>
				</div>
			</div>
		</div>
	</transition>
</template>

<style scoped>
.ux-modal-scrim {
	position: fixed;
	inset: 0;
	z-index: 80;
	display: flex;
	align-items: center;
	justify-content: center;
	padding: 20px;
	background: rgba(20, 17, 10, 0.5);
	backdrop-filter: blur(4px);
}
.ux-modal {
	width: min(440px, 100%);
	background: var(--ux-surface);
	border: 1px solid var(--ux-border);
	border-radius: 20px;
	box-shadow: 0 30px 80px rgba(20, 17, 10, 0.35);
	overflow: hidden;
}
.ux-modal-head {
	display: flex;
	gap: 14px;
	align-items: flex-start;
	padding: 24px 24px 12px;
}
.ux-modal-icon {
	width: 44px;
	height: 44px;
	border-radius: 13px;
	flex-shrink: 0;
	display: flex;
	align-items: center;
	justify-content: center;
}
.tone-primary .ux-modal-icon { background: linear-gradient(150deg, #1c1710, #2a2114); color: var(--ux-gold-soft); }
.tone-gold .ux-modal-icon { background: linear-gradient(150deg, #c9a227, #e6c757); color: #221d12; }
.tone-danger .ux-modal-icon { background: rgba(180, 69, 47, 0.12); color: #b4452f; }
.ux-modal-title { margin: 2px 0 0; font-size: 18px; font-weight: 700; color: var(--ux-text); }
.ux-modal-sub { margin: 4px 0 0; font-size: 13px; color: var(--ux-text-dim); line-height: 1.45; }
.ux-modal-body { padding: 6px 24px 4px; }
.ux-modal-body:empty { display: none; }
.ux-modal-foot {
	display: flex;
	justify-content: flex-end;
	gap: 10px;
	padding: 18px 24px 22px;
}
.ux-modal-spin {
	width: 13px; height: 13px; border-radius: 50%;
	border: 2px solid currentColor; border-right-color: transparent;
	display: inline-block; margin-right: 6px; vertical-align: -1px;
	animation: ux-spin 0.7s linear infinite;
}
@keyframes ux-spin { to { transform: rotate(360deg); } }

.ux-modal-enter-active, .ux-modal-leave-active { transition: opacity 0.2s ease; }
.ux-modal-enter-active .ux-modal, .ux-modal-leave-active .ux-modal { transition: transform 0.24s cubic-bezier(0.34, 1.56, 0.64, 1); }
.ux-modal-enter-from, .ux-modal-leave-to { opacity: 0; }
.ux-modal-enter-from .ux-modal, .ux-modal-leave-to .ux-modal { transform: translateY(16px) scale(0.96); }
</style>
