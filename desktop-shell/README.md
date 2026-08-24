# Desktop Shell

The desktop-shell engine is responsible for packaging and installing the application as a desktop-native executable. It owns the build pipeline that produces a distributable, installable desktop app (not a web app served from the cloud) and ensures it runs offline on low-spec hardware per the Core Engine Philosophy. If this engine is deleted, the app cannot be packaged or installed as a desktop application; all engines continue to exist but have no distribution surface.
