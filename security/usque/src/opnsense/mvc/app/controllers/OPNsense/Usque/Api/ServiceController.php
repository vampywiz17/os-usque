<?php

namespace OPNsense\Usque\Api;

use OPNsense\Base\ApiControllerBase;
use OPNsense\Core\Backend;

class ServiceController extends ApiControllerBase
{
    private function run(string $action): array
    {
        if (!$this->request->isPost()) {
            return ['status' => 'failed', 'message' => 'POST required'];
        }
        $response = trim((new Backend())->configdRun("usque {$action}"));
        return ['status' => 'ok', 'response' => $response];
    }

    public function reconfigureAction(): array
    {
        if (!$this->request->isPost()) {
            return ['status' => 'failed', 'message' => 'POST required'];
        }
        $backend = new Backend();
        $template = trim($backend->configdRun('template reload OPNsense/Usque'));
        $service = trim($backend->configdRun('usque restart'));
        $runtime = json_decode(trim($backend->configdRun('usque status')), true);
        $healthy = is_array($runtime) && ($runtime['status'] ?? '') === 'ok';
        $failed = [];
        foreach ($runtime['instances'] ?? [] as $instance) {
            if (empty($instance['running'])) {
                $healthy = false;
                $failed[] = sprintf(
                    '%s (%s)',
                    $instance['interface'] ?? '?',
                    $instance['role'] ?? '?'
                );
            }
        }
        $message = $service;
        if (!$healthy && empty($message)) {
            $message = !empty($failed)
                ? sprintf(
                    gettext('Tunnel process did not start: %s. Check the instance syslog for details.'),
                    implode(', ', $failed)
                )
                : gettext('Unable to read the managed tunnel runtime state.');
        }
        return [
            'status' => $healthy ? 'ok' : 'failed',
            'template' => $template,
            'response' => $service,
            'runtime' => $runtime,
            'message' => $message,
        ];
    }

    public function startAction(): array
    {
        return $this->run('start');
    }

    public function stopAction(): array
    {
        return $this->run('stop');
    }

    public function restartAction(): array
    {
        return $this->run('restart');
    }

    public function statusAction(): array
    {
        return $this->run('status');
    }
}
