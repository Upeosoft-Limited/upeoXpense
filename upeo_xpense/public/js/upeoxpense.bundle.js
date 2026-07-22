import { createApp } from "vue";
import App from "./upeoxpense/App.vue";

const boot = window.upeoxpense || {};
const app = createApp(App, { boot });
app.mount("#upeoxpense-app");

// Remove the server-rendered boot spinner once Vue has taken over.
const spinner = document.getElementById("upeoxpense-boot");
if (spinner) spinner.remove();
