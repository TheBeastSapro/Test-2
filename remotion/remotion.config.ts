/**
 * Render defaults for headless, server-side use.
 *
 * The Chromium flags matter in a container: a headless Chrome without
 * --no-sandbox will not start as a non-root user in Docker, and the default
 * /dev/shm is 64MB, which a 1080p render exhausts and then crashes with a
 * message that says nothing about shared memory.
 */
import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setChromiumDisableWebSecurity(false);
Config.setChromiumOpenGlRenderer("swiftshader");
