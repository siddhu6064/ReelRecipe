module.exports = function (api) {
  api.cache(true)
  return {
    presets: ['babel-preset-expo'],
    plugins: [
      // Required for Expo Router file-based routing
      'expo-router/babel',
      // Required for React Native Reanimated (used by gesture handler, bottom sheets)
      'react-native-reanimated/plugin',
    ],
  }
}
