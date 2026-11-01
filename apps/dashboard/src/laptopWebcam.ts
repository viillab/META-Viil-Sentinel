/** Browser-only, local-origin webcam demo. Never posts frames or audio anywhere. */

export const LAPTOP_WEBCAM_DEMO_MAX_MS = 60_000;
export const LOCAL_WEBCAM_HOSTS = Object.freeze(["127.0.0.1", "localhost", "[::1]"]);

export function webcamDemoSupported(
  hostname: string,
  isSecureContext: boolean,
  devices: Pick<MediaDevices, "getUserMedia"> | null | undefined,
): boolean {
  return LOCAL_WEBCAM_HOSTS.includes(hostname.toLowerCase())
    && isSecureContext === true
    && typeof devices?.getUserMedia === "function";
}

export async function requestLaptopWebcam(
  devices: Pick<MediaDevices, "getUserMedia">,
): Promise<MediaStream> {
  return devices.getUserMedia({
    audio: false,
    video: {
      width: { ideal: 640 },
      height: { ideal: 360 },
      frameRate: { ideal: 15, max: 24 },
    },
  });
}

export function stopLaptopWebcam(stream: Pick<MediaStream, "getTracks"> | null): void {
  if (!stream) return;
  for (const track of stream.getTracks()) track.stop();
}

export function hasUsableVideoTrack(stream: MediaStream): boolean {
  return stream.getVideoTracks().some(track => track.readyState === "live");
}

export function webcamErrorLabel(error: unknown): string {
  const name = error instanceof Error ? error.name : "";
  switch (name) {
    case "NotAllowedError":
    case "PermissionDeniedError":
      return "Camera permission denied. Allow camera access in your browser and Windows settings.";
    case "NotFoundError":
    case "DevicesNotFoundError":
      return "No laptop camera was found by this browser.";
    case "NotReadableError":
    case "TrackStartError":
      return "Camera is in use or unavailable. Close other apps using the webcam.";
    default:
      return "Unable to start laptop webcam. No frames were saved or uploaded.";
  }
}
