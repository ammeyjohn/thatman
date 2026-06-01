<script setup lang="ts">
import { ref } from 'vue'

const message = ref('道友，欢迎来到修仙世界')
const subtitle = ref('上古劫后，遗落世道')
</script>

<template>
  <div class="min-h-screen flex flex-col items-center justify-center px-4">
    <!-- 装饰分隔符 -->
    <div class="text-text-gold text-lg tracking-widest mb-8 opacity-80">
      ☁️ ☁️ ☁️ ☁️ ☁️ ☁️ ☁️ ☁️ ☁️ ☁️
    </div>

    <!-- 主标题 -->
    <h1 class="text-4xl md:text-6xl font-bold text-text-gold mb-4 text-center tracking-wider">
      {{ message }}
    </h1>

    <!-- 副标题 -->
    <p class="text-xl md:text-2xl text-text-cyan mb-8 text-center tracking-wide animate-breathe">
      {{ subtitle }}
    </p>

    <!-- 装饰分隔符 -->
    <div class="text-text-gold text-lg tracking-widest mb-12 opacity-80">
      ◈ ─────────────────────────────────────── ◈
    </div>

    <!-- 状态卡片 -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl w-full">
      <div class="bg-bg-ink/50 border border-text-gold/30 rounded-lg p-6 hover-glow">
        <div class="text-text-gold text-sm mb-2">⚡ 框架状态</div>
        <div class="text-text-jade">运行正常</div>
      </div>

      <div class="bg-bg-ink/50 border border-text-cyan/30 rounded-lg p-6 hover-glow">
        <div class="text-text-cyan text-sm mb-2">🜁 技术栈</div>
        <div class="text-text-jade">Vue3 + Vite + TS</div>
      </div>

      <div class="bg-bg-ink/50 border border-text-purple/30 rounded-lg p-6 hover-glow">
        <div class="text-text-purple text-sm mb-2">✨ 组件库</div>
        <div class="text-text-jade">shadcn/ui Ready</div>
      </div>
    </div>

    <!-- 底部装饰 -->
    <div class="mt-16 text-text-gray text-sm tracking-wider">
      <p>┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓</p>
      <p class="my-2">  天地不仁，以万物为刍狗</p>
      <p>┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛</p>
    </div>
  </div>
</template>
