/**
 * Media Coordinator - ensures only one media player (video or article reader) plays at a time
 * Uses a simple registry pattern that both contexts can access
 */

type StopFunction = () => void

interface MediaCoordinator {
  videoStop: StopFunction | null
  articleStop: StopFunction | null
}

// Global coordinator instance
const coordinator: MediaCoordinator = {
  videoStop: null,
  articleStop: null,
}

export function registerVideoPlayer(stopFn: StopFunction) {
  coordinator.videoStop = stopFn
}

export function registerArticleReader(stopFn: StopFunction) {
  coordinator.articleStop = stopFn
}

export function stopVideoPlayer() {
  if (coordinator.videoStop) {
    coordinator.videoStop()
  }
}

export function stopArticleReader() {
  if (coordinator.articleStop) {
    coordinator.articleStop()
  }
}
