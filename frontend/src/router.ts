import { createRouter, createWebHistory } from "vue-router";
import JobDetail from "./pages/JobDetail.vue";
import NewJob from "./pages/NewJob.vue";

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: NewJob },
    { path: "/jobs/:jobId", component: JobDetail, props: true },
  ],
});

