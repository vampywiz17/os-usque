PORTNAME=	usque-nativetun
DISTVERSION=	0.7.0
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
GH_TAGNAME=	f679abe2c90011255bbf692a6492dcde46c09947

.include "Makefile.crates"

PLIST_FILES=	bin/usque-nativetun

.include <bsd.port.mk>
