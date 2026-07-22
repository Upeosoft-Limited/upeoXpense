<script setup>
defineProps({ open: Boolean, title: String, subtitle: String });
const emit = defineEmits(["close"]);
</script>

<template>
	<transition name="ux-drawer">
		<div v-if="open" class="ux-drawer-scrim" @click.self="emit('close')">
			<aside class="ux-drawer">
				<header class="ux-drawer-head">
					<div>
						<h3 class="ux-drawer-title">{{ title }}</h3>
						<p v-if="subtitle" class="ux-drawer-sub">{{ subtitle }}</p>
					</div>
					<button class="ux-icon-btn" @click="emit('close')" aria-label="Close">
						<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<path d="M18 6 6 18M6 6l12 12" stroke-linecap="round" />
						</svg>
					</button>
				</header>
				<div class="ux-drawer-body">
					<slot />
				</div>
				<footer v-if="$slots.footer" class="ux-drawer-foot">
					<slot name="footer" />
				</footer>
			</aside>
		</div>
	</transition>
</template>

<style scoped>
.ux-drawer-scrim {
	position: fixed;
	inset: 0;
	background: rgba(20, 17, 10, 0.45);
	backdrop-filter: blur(2px);
	display: flex;
	justify-content: flex-end;
	z-index: 60;
}
.ux-drawer {
	width: min(480px, 100%);
	height: 100%;
	background: var(--ux-bg);
	border-left: 1px solid var(--ux-border);
	display: flex;
	flex-direction: column;
	box-shadow: -20px 0 50px rgba(20, 17, 10, 0.18);
}
.ux-drawer-head {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	padding: 20px 22px 16px;
	border-bottom: 1px solid var(--ux-border);
}
.ux-drawer-title { margin: 0; font-size: 17px; font-weight: 700; color: var(--ux-text); }
.ux-drawer-sub { margin: 3px 0 0; font-size: 12.5px; color: var(--ux-text-dim); }
.ux-drawer-body { flex: 1; overflow-y: auto; padding: 20px 22px; }
.ux-drawer-foot { padding: 16px 22px; border-top: 1px solid var(--ux-border); background: var(--ux-surface); display: flex; gap: 10px; }
.ux-icon-btn {
	border: 1px solid var(--ux-border);
	background: var(--ux-surface);
	color: var(--ux-text-dim);
	width: 32px; height: 32px;
	border-radius: 9px;
	cursor: pointer;
	display: inline-flex; align-items: center; justify-content: center;
}
.ux-icon-btn:hover { color: var(--ux-text); border-color: var(--ux-gold); }

.ux-drawer-enter-active, .ux-drawer-leave-active { transition: opacity 0.2s ease; }
.ux-drawer-enter-active .ux-drawer, .ux-drawer-leave-active .ux-drawer { transition: transform 0.24s cubic-bezier(0.4, 0, 0.2, 1); }
.ux-drawer-enter-from, .ux-drawer-leave-to { opacity: 0; }
.ux-drawer-enter-from .ux-drawer, .ux-drawer-leave-to .ux-drawer { transform: translateX(40px); }
</style>
