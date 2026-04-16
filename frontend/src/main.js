import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import Dashboard from "./views/Dashboard.vue";
import Findings from "./views/Findings.vue";
import BuildDetail from "./views/BuildDetail.vue";
import Exemptions from "./views/Exemptions.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: Dashboard },
    { path: "/findings", component: Findings },
    { path: "/builds/:id", component: BuildDetail },
    { path: "/exemptions", component: Exemptions },
  ],
});

createApp(App).use(router).mount("#app");
