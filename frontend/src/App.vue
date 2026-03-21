<template>
  <div class="min-h-screen bg-slate-50 text-slate-900">
    <header class="border-b bg-white">
      <div class="mx-auto flex max-w-5xl items-baseline justify-between px-4 py-4">
        <h1 class="text-lg font-semibold">自动化深度研究助手</h1>
        <nav class="flex gap-4 text-sm text-slate-600">
          <RouterLink class="hover:text-slate-900" to="/">新建任务</RouterLink>
        </nav>
      </div>
    </header>

    <main class="mx-auto max-w-5xl px-4 py-6">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts"></script>

