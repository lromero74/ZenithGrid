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

/** Register the video player's stop fn. Returns an unregister cleanup that
 *  clears the slot only if it still points at this fn (so a newer registration
 *  isn't clobbered by a late-unmounting older one). */
export function registerVideoPlayer(stopFn: StopFunction): () => void {
  coordinator.videoStop = stopFn
  return () => {
    if (coordinator.videoStop === stopFn) coordinator.videoStop = null
  }
}

/** Register the article reader's stop fn. Returns an unregister cleanup. */
export function registerArticleReader(stopFn: StopFunction): () => void {
  coordinator.articleStop = stopFn
  return () => {
    if (coordinator.articleStop === stopFn) coordinator.articleStop = null
  }
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
