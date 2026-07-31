<?php

/*
 * Copyright (C) 2026 os-usque contributors
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the conditions in LICENSE are met.
 * THIS SOFTWARE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND.
 */

namespace OPNsense\Usque\Api;

use OPNsense\Base\ApiControllerBase;
use OPNsense\Core\Backend;
use OPNsense\Usque\Usque;

class EnrollmentController extends ApiControllerBase
{
    private const UUID_PATTERN = '/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i';
    private const JOB_PATTERN = '/^[0-9a-f]{32}$/';
    private const MAX_TOKEN_BYTES = 65536;

    private function getClientTunnel($uuid)
    {
        if (!is_string($uuid) || preg_match(self::UUID_PATTERN, $uuid) !== 1) {
            return null;
        }
        $node = (new Usque())->getNodeByReference('tunnels.tunnel.' . $uuid);
        if ($node === null || (string)$node->role !== 'client') {
            return null;
        }
        return $node;
    }

    private function extractToken($input, $team)
    {
        if (!is_string($input) || strlen($input) > self::MAX_TOKEN_BYTES) {
            return null;
        }
        $input = trim($input);
        if ($input === '' || strpos($input, "\0") !== false) {
            return null;
        }

        if (stripos($input, 'com.cloudflare.warp://') === 0) {
            $uri = parse_url($input);
            $expectedHost = strtolower($team . '.cloudflareaccess.com');
            if (
                !is_array($uri) ||
                strtolower($uri['scheme'] ?? '') !== 'com.cloudflare.warp' ||
                strtolower($uri['host'] ?? '') !== $expectedHost ||
                ($uri['path'] ?? '') !== '/auth'
            ) {
                return null;
            }
            parse_str($uri['query'] ?? '', $query);
            $input = is_string($query['token'] ?? null) ? $query['token'] : '';
        }

        if ($input === '' || preg_match('/\s/', $input) === 1) {
            return null;
        }
        return $input;
    }

    public function loginUrlAction($uuid)
    {
        if (!$this->request->isPost()) {
            return ['status' => 'failed'];
        }
        $node = $this->getClientTunnel($uuid);
        if ($node === null) {
            return ['status' => 'failed', 'message' => gettext('Select an egress client tunnel.')];
        }
        $team = strtolower((string)$node->team);
        if ($team === '' || preg_match('/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/', $team) !== 1) {
            return ['status' => 'failed', 'message' => gettext('Configure a valid Cloudflare team name first.')];
        }
        return [
            'status' => 'ok',
            'url' => 'https://' . $team . '.cloudflareaccess.com/warp',
        ];
    }

    public function registerAction($uuid)
    {
        if (!$this->request->isPost()) {
            return ['status' => 'failed'];
        }
        $node = $this->getClientTunnel($uuid);
        if ($node === null) {
            return ['status' => 'failed', 'message' => gettext('Select an egress client tunnel.')];
        }
        if ((string)$this->request->getPost('accept_tos') !== '1') {
            return ['status' => 'failed', 'message' => gettext('Cloudflare Terms of Service must be accepted explicitly.')];
        }

        $team = strtolower((string)$node->team);
        $token = $this->extractToken($this->request->getPost('token'), $team);
        if ($token === null) {
            return ['status' => 'failed', 'message' => gettext('The enrollment token or callback URI is invalid.')];
        }

        $jobId = bin2hex(random_bytes(16));
        $tokenPath = '/var/tmp/usque-enroll-' . $jobId . '.jwt';
        $handle = @fopen($tokenPath, 'x+b');
        if ($handle === false || !@chmod($tokenPath, 0600)) {
            if (is_resource($handle)) {
                fclose($handle);
            }
            @unlink($tokenPath);
            return ['status' => 'failed', 'message' => gettext('Unable to create the private enrollment handoff.')];
        }

        $written = fwrite($handle, $token);
        $tokenLength = strlen($token);
        $flushed = fflush($handle);
        fclose($handle);
        unset($token);
        if ($written !== $tokenLength || !$flushed) {
            @unlink($tokenPath);
            return ['status' => 'failed', 'message' => gettext('Unable to write the private enrollment handoff.')];
        }

        try {
            (new Backend())->configdpRun('usque client_register', [$jobId, strtolower($uuid)], true);
        } catch (\Throwable $error) {
            @unlink($tokenPath);
            return ['status' => 'failed', 'message' => gettext('Unable to start the enrollment job.')];
        }
        return ['status' => 'started', 'job_id' => $jobId];
    }

    public function statusAction($jobId)
    {
        if (
            !$this->request->isPost() ||
            !is_string($jobId) ||
            preg_match(self::JOB_PATTERN, $jobId) !== 1
        ) {
            return ['state' => 'failed', 'message' => gettext('Invalid enrollment job.')];
        }

        $response = trim((new Backend())->configdpRun('usque client_register_status', [$jobId]));
        $decoded = json_decode($response, true);
        if (!is_array($decoded)) {
            return ['state' => 'waiting', 'message' => gettext('Waiting for the enrollment worker.')];
        }
        return $decoded;
    }
}
