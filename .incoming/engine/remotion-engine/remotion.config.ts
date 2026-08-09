import {Config} from '@remotion/cli/config';

// Frame capture: PNG keeps type edges crisp (JPEG would chroma-subsample the red accent twice).
Config.setVideoImageFormat('png');
Config.setCodec('h264');
// Explicit ABR, not CRF: this content is mostly flat white + dark grain, so CRF 16
// only lands ~1.6 Mbps and gets QC-failed on the bitrate check. 14 Mbps is the floor.
Config.setVideoBitrate('14M');
Config.setPixelFormat('yuv420p');
Config.setX264Preset('slow');
Config.setOverwriteOutput(true);
Config.setConcurrency(2);
Config.setChromiumOpenGlRenderer('swangle');
Config.setChromiumDisableWebSecurity(true);
