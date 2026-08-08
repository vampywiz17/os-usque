PORTNAME=	usque-nativetun
DISTVERSION=	0.8.2
CATEGORIES=	security net-vpn

MAINTAINER=	vampywiz17@users.noreply.github.com
COMMENT=	Native FreeBSD TUN client for Cloudflare MASQUE CONNECT-IP
WWW=		https://github.com/vampywiz17/usque-rs-bsd

LICENSE=	MIT
LICENSE_FILE=	${WRKSRC}/LICENSE.md

USES=		cargo cmake:indirect ninja:build pkgconfig

USE_GITHUB=	yes
GH_ACCOUNT=	vampywiz17
GH_PROJECT=	usque-rs-bsd
GH_TAGNAME=	99d00c7634d88a0dbb08b921c8b617b37483ae4c

.include "Makefile.crates"

PLIST_FILES=	bin/usque-nativetun

.include <bsd.port.mk>
