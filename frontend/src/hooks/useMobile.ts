import { useSyncExternalStore } from "react"

const MOBILE_QUERY = "(max-width: 767px)"

function subscribe(onChange: () => void) {
  const media = window.matchMedia(MOBILE_QUERY)
  media.addEventListener("change", onChange)
  return () => media.removeEventListener("change", onChange)
}

function getSnapshot() {
  return window.matchMedia(MOBILE_QUERY).matches
}

// The first hydration render must match the desktop server snapshot. React
// subscribes and updates to the real viewport immediately after hydration.
export function useIsMobile() {
  return useSyncExternalStore(subscribe, getSnapshot, () => false)
}
