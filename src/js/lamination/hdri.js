/**
 * The photographed studio every steel surface reflects: Poly Haven
 * "Studio Small 02" (CC0, polyhaven.com), 1k equirectangular HDR. A dark room
 * with defined soft boxes gives steel real highlight-and-shadow banding;
 * bright, white-walled studios wash bare metal out to grey paper.
 */
export const STUDIO_HDRI = {
  url: '/hdri/studio_small_02.hdr',
  // half-size copy for the small product visuals: same light, a quarter of the bytes.
  // The full-screen intro keeps the 1k original; at that size the smaller map makes
  // the moving highlights step instead of glide.
  miniUrl: '/hdri/studio_small_02-512.hdr',
  rotation: 3.4, // radians about Y: a soft box behind the camera for the coil's end face
  miniRotation: [-0.5, 3.4], // [x, y] for the small product visuals
};
