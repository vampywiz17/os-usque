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
    private const MAX_SERVICE_TOKEN_BYTES = 8192;
    private const MAX_ACCESS_CLIENT_ID_BYTES = 512;
    private const MAX_ACCESS_CLIENT_SECRET_BYTES = 4096;
    private const TEAM_PATTERN = '/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/';

    private function getTunnel($uuid, string $role)
    {
        if (!is_string($uuid) || preg_match(self::UUID_PATTERN, $uuid) !== 1) {
            return null;
        }
        $node = (new Usque())->getNodeByReference('tunnels.tunnel.' . $uuid);
        if ($node === null || (string)$node->role !== $role) {
            return null;
        }
        return $node;
    }

    private function getClientTunnel($uuid)
    {
        return $this->getTunnel($uuid, 'client');
    }

    private function getMeshTunnel($uuid)
    {
        return $this->getTunnel($uuid, 'mesh-node');
    }

    private function getRegistrationState($uuid, string $role)
    {
        try {
            $response = trim(
                (new Backend())->configdpRun(
                    'usque client_registration_status',
                    [strtolower($uuid), $role]
                )
            );
            $decoded = json_decode($response, true);
        } catch (\Throwable $error) {
            $decoded = null;
        }

        if (
            !is_array($decoded) ||
            !is_string($decoded['status'] ?? null) ||
            !is_bool($decoded['registered'] ?? null) ||
            !is_bool($decoded['can_register'] ?? null)
        ) {
            return [
                'status' => 'failed',
                'registered' => false,
                'can_register' => false,
                'message' => gettext('Unable to determine the tunnel registration state.'),
            ];
        }

        return [
            'status' => $decoded['status'],
            'registered' => $decoded['registered'],
            'can_register' => $decoded['can_register'],
            'message' => is_string($decoded['message'] ?? null) ? $decoded['message'] : '',
        ];
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

    public function registrationStatusAction($uuid)
    {
        if (!$this->request->isPost()) {
            return ['status' => 'failed', 'registered' => false, 'can_register' => false];
        }
        $node = $this->getClientTunnel($uuid) ?? $this->getMeshTunnel($uuid);
        if ($node === null) {
            return [
                'status' => 'failed',
                'registered' => false,
                'can_register' => false,
                'message' => gettext('Select an egress client or ingress Mesh tunnel.'),
            ];
        }
        return $this->getRegistrationState($uuid, (string)$node->role);
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
        if ($team === '' || preg_match(self::TEAM_PATTERN, $team) !== 1) {
            return ['status' => 'failed', 'message' => gettext('Configure a valid Cloudflare team name first.')];
        }
        return [
            'status' => 'ok',
            'url' => 'https://' . $team . '.cloudflareaccess.com/warp',
        ];
    }

    private function startHandoff($uuid, string $payload, string $suffix, string $action)
    {
        $jobId = bin2hex(random_bytes(16));
        $handoffPath = '/var/tmp/usque-enroll-' . $jobId . '.' . $suffix;
        $handle = @fopen($handoffPath, 'x+b');
        if ($handle === false || !@chmod($handoffPath, 0600)) {
            if (is_resource($handle)) {
                fclose($handle);
            }
            @unlink($handoffPath);
            return ['status' => 'failed', 'message' => gettext('Unable to create the private enrollment handoff.')];
        }

        $length = strlen($payload);
        $offset = 0;
        while ($offset < $length) {
            $written = fwrite($handle, substr($payload, $offset));
            if ($written === false || $written === 0) {
                break;
            }
            $offset += $written;
        }
        $flushed = fflush($handle);
        fclose($handle);
        unset($payload);
        if ($offset !== $length || !$flushed) {
            @unlink($handoffPath);
            return ['status' => 'failed', 'message' => gettext('Unable to write the private enrollment handoff.')];
        }

        try {
            (new Backend())->configdpRun('usque ' . $action, [$jobId, strtolower($uuid)], true);
        } catch (\Throwable $error) {
            @unlink($handoffPath);
            return ['status' => 'failed', 'message' => gettext('Unable to start the enrollment job.')];
        }
        return ['status' => 'started', 'job_id' => $jobId];
    }

    private function startRegistration($uuid, string $token, string $action)
    {
        return $this->startHandoff($uuid, $token, 'jwt', $action);
    }

    private function singleLineValue($value, int $maximumBytes)
    {
        if (
            !is_string($value) ||
            $value === '' ||
            strlen($value) > $maximumBytes ||
            strpos($value, "\0") !== false ||
            strpos($value, "\r") !== false ||
            strpos($value, "\n") !== false
        ) {
            return null;
        }
        return $value;
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
        $registration = $this->getRegistrationState($uuid, 'client');
        if (!$registration['can_register']) {
            return ['status' => 'failed', 'message' => $registration['message']];
        }
        if ((string)$this->request->getPost('accept_tos') !== '1') {
            return ['status' => 'failed', 'message' => gettext('Cloudflare Terms of Service must be accepted explicitly.')];
        }

        $team = strtolower((string)$node->team);
        $token = $this->extractToken($this->request->getPost('token'), $team);
        if ($token === null) {
            return ['status' => 'failed', 'message' => gettext('The enrollment token or callback URI is invalid.')];
        }
        return $this->startRegistration($uuid, $token, 'client_register');
    }

    public function serviceTokenRegisterAction($uuid)
    {
        if (!$this->request->isPost()) {
            return ['status' => 'failed'];
        }
        if ($this->getClientTunnel($uuid) === null) {
            return ['status' => 'failed', 'message' => gettext('Select an egress client tunnel.')];
        }
        $registration = $this->getRegistrationState($uuid, 'client');
        if (!$registration['can_register']) {
            return ['status' => 'failed', 'message' => $registration['message']];
        }
        if ((string)$this->request->getPost('accept_tos') !== '1') {
            return ['status' => 'failed', 'message' => gettext('Cloudflare Terms of Service must be accepted explicitly.')];
        }

        $organization = $this->singleLineValue($this->request->getPost('organization'), 63);
        $clientId = $this->singleLineValue(
            $this->request->getPost('auth_client_id'),
            self::MAX_ACCESS_CLIENT_ID_BYTES
        );
        $clientSecret = $this->singleLineValue(
            $this->request->getPost('auth_client_secret'),
            self::MAX_ACCESS_CLIENT_SECRET_BYTES
        );
        if ($organization === null || preg_match(self::TEAM_PATTERN, strtolower($organization)) !== 1) {
            return ['status' => 'failed', 'message' => gettext('Enter a valid Cloudflare organization team name.')];
        }
        if ($clientId === null || substr($clientId, -7) !== '.access') {
            return ['status' => 'failed', 'message' => gettext('Enter a valid Cloudflare Access Client ID ending in .access.')];
        }
        if ($clientSecret === null) {
            return ['status' => 'failed', 'message' => gettext('Enter a valid Cloudflare Access Client Secret.')];
        }

        $payload = json_encode([
            'organization' => strtolower($organization),
            'auth_client_id' => $clientId,
            'auth_client_secret' => $clientSecret,
        ], JSON_UNESCAPED_SLASHES);
        unset($clientSecret);
        if (!is_string($payload) || strlen($payload) > self::MAX_SERVICE_TOKEN_BYTES) {
            return ['status' => 'failed', 'message' => gettext('The service-token enrollment parameters are too large.')];
        }
        return $this->startHandoff(
            $uuid,
            $payload,
            'service-token',
            'client_service_token_register'
        );
    }


    public function meshRegisterAction($uuid)
    {
        if (!$this->request->isPost()) {
            return ['status' => 'failed'];
        }
        if ($this->getMeshTunnel($uuid) === null) {
            return ['status' => 'failed', 'message' => gettext('Select an ingress Mesh tunnel.')];
        }
        $registration = $this->getRegistrationState($uuid, 'mesh-node');
        if (!$registration['can_register']) {
            return ['status' => 'failed', 'message' => $registration['message']];
        }
        if ((string)$this->request->getPost('accept_tos') !== '1') {
            return ['status' => 'failed', 'message' => gettext('Cloudflare Terms of Service must be accepted explicitly.')];
        }
        if ((string)$this->request->getPost('acknowledge_linux_platform_claim') !== '1') {
            return [
                'status' => 'failed',
                'message' => gettext('The Linux platform compatibility claim and its risks must be acknowledged explicitly.'),
            ];
        }

        $token = $this->extractToken($this->request->getPost('token'), '');
        if ($token === null) {
            return ['status' => 'failed', 'message' => gettext('The Mesh connector token is invalid.')];
        }
        return $this->startRegistration($uuid, $token, 'mesh_register');
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
