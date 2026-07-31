<?php

/*
 * Copyright (C) 2026 os-usque contributors
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice,
 *    this list of conditions and the following disclaimer.
 *
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES,
 * INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
 * AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 * AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY,
 * OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 */

function usque_devices()
{
    $names = [];

    foreach ((new OPNsense\Usque\Usque())->tunnels->tunnel->iterateItems() as $node) {
        if (empty((string)$node->enabled)) {
            continue;
        }

        $interface = (string)$node->interface;
        if (!preg_match('/^tun[0-9]{1,3}$/D', $interface)) {
            continue;
        }

        $name = (string)$node->name;
        $role = (string)$node->role === 'mesh-node' ? gettext('Mesh node') : gettext('egress client');
        $names[$interface] = [
            'descr' => sprintf('%s (usque %s - %s)', $interface, $role, $name),
            'ifdescr' => $name,
            'name' => $interface,
        ];
    }

    return [[
        /*
         * usque-nativetun/tun-rs owns device creation and addressing. This
         * hook only exposes configured native TUN names to the OPNsense
         * assignment API, following the standard virtual-device contract.
         */
        'configurable' => false,
        'pattern' => '^tun[0-9]{1,3}$',
        'spoofmac' => false,
        'type' => 'usque',
        'volatile' => true,
        'names' => $names,
    ]];
}
