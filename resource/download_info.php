<?php
header('Content-Type: application/json; charset=utf-8');

$zipPath = dirname(__DIR__) . '/qPTM_all_data.zip';

if (is_file($zipPath)) {
    echo json_encode(['size' => filesize($zipPath), 'ready' => true]);
} else {
    echo json_encode(['size' => null, 'ready' => false]);
}
