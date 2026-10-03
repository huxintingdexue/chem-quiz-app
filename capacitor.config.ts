import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.ttc.chemquiz',
  appName: '化学三轮复习',
  webDir: 'android-shell',
  server: {
    url: 'https://guang-ttc.github.io/chem-quiz-app/',
    cleartext: false,
  },
};

export default config;
