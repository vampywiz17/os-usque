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

namespace OPNsense\Usque\Api;

use OPNsense\Base\ApiMutableModelControllerBase;
use OPNsense\Core\Backend;
use OPNsense\Core\Config;

class SettingsController extends ApiMutableModelControllerBase
{

    public function getGeneralAction()
    {
        if ($this->request->isGet()) {
            return ['general' => $this->getModel()->general->getNodes()];
        }
        return [];
    }

    public function setGeneralAction()
    {
        $result = ['result' => 'failed'];
        if ($this->request->isPost() && $this->request->hasPost('general')) {
            Config::getInstance()->lock();
            $node = $this->getModel()->general;
            $node->setNodes($this->request->getPost('general'));
            $result = $this->validate($node, 'general', true);
            if (empty($result['validations'])) {
                $this->setBaseHook($node);
                return $this->save(false, true);
            }
            $result['result'] = 'failed';
        }
        return $result;
    }

    protected static $internalModelName = 'usque';
    protected static $internalModelClass = '\OPNsense\Usque\Usque';
    protected static $internalModelUseSafeDelete = true;
    public function searchTunnelAction()
    {
        return $this->searchBase(
            'tunnels.tunnel',
            ['enabled', 'name', 'role', 'interface', 'team', 'description'],
            'name'
        );
    }

    public function getTunnelAction($uuid = null)
    {
        return $this->getBase('tunnel', 'tunnels.tunnel', $uuid);
    }

    public function addTunnelAction()
    {
        return $this->addBase('tunnel', 'tunnels.tunnel');
    }

    public function setTunnelAction($uuid)
    {
        return $this->setBase('tunnel', 'tunnels.tunnel', $uuid);
    }

    public function delTunnelAction($uuid)
    {
        if (
            !$this->request->isPost() ||
            !is_string($uuid) ||
            preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i', $uuid) !== 1
        ) {
            return ['result' => 'failed', 'message' => gettext('Invalid tunnel deletion request.')];
        }

        $model = $this->getModel();
        if (!empty((string)$model->general->enabled)) {
            return [
                'result' => 'failed',
                'message' => gettext('Disable the usque service and apply the change before deleting a tunnel.'),
            ];
        }
        $node = $model->getNodeByReference('tunnels.tunnel.' . $uuid);
        if ($node === null || !in_array((string)$node->role, ['client', 'mesh-node'], true)) {
            return ['result' => 'failed', 'message' => gettext('The tunnel does not exist or has an invalid role.')];
        }

        try {
            $response = trim(
                (new Backend())->configdpRun(
                    'usque delete_registration',
                    [strtolower($uuid), (string)$node->role]
                )
            );
            $decoded = json_decode($response, true);
        } catch (\Throwable $error) {
            $decoded = null;
        }
        if (!is_array($decoded) || ($decoded['status'] ?? '') !== 'ok') {
            return [
                'result' => 'failed',
                'message' => is_string($decoded['message'] ?? null)
                    ? $decoded['message']
                    : gettext('Unable to remove the private tunnel registration.'),
            ];
        }
        return $this->delBase('tunnels.tunnel', $uuid);
    }

    public function toggleTunnelAction($uuid, $enabled = null)
    {
        return $this->toggleBase('tunnels.tunnel', $uuid, $enabled);
    }
}
