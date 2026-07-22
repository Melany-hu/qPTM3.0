<?php
header('Content-Type: application/json; charset=utf-8');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['success' => false, 'message' => 'Method not allowed.']);
    exit;
}

require_once __DIR__ . '/email.php';

$title       = trim($_POST['title'] ?? '');
$firstname   = trim($_POST['firstname'] ?? '');
$lastname    = trim($_POST['lastname'] ?? '');
$affiliation = trim($_POST['affiliation'] ?? '');
$country     = trim($_POST['country'] ?? '');
$email       = trim($_POST['email'] ?? '');
$msg         = trim($_POST['msg'] ?? '');

$required = [
    'title'       => $title,
    'firstname'   => $firstname,
    'lastname'    => $lastname,
    'affiliation' => $affiliation,
    'country'     => $country,
    'email'       => $email,
];

foreach ($required as $field => $value) {
    if ($value === '') {
        echo json_encode(['success' => false, 'message' => 'Please fill in all required fields.']);
        exit;
    }
}

if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
    echo json_encode(['success' => false, 'message' => 'Please enter a valid email address.']);
    exit;
}

if ($msg === '' || !ctype_digit($msg)) {
    echo json_encode(['success' => false, 'message' => 'Please complete the verification.']);
    exit;
}

$dataset   = 'qPTM';
$filea     = 'qPTM_all_data.zip';
$zipPath   = dirname(__DIR__) . '/' . $filea;
$datasetLabel = 'All PTM sites with quantification values';

if (!is_file($zipPath)) {
    echo json_encode(['success' => false, 'message' => 'Dataset file is not available yet. Please try again later or contact us.']);
    exit;
}

$logLine = "\r\n" . date('Ymd H:i:s') . "\t{$dataset}\t{$title}\t{$firstname}\t{$lastname}\t{$affiliation}\t{$country}\t{$email}\r\n";
file_put_contents(dirname(__DIR__) . '/download_' . $dataset . '_list.txt', $logLine, FILE_APPEND);

$code = new code();
$protocol = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
$host = $_SERVER['HTTP_HOST'] ?? 'localhost';
$basePath = rtrim(dirname(dirname($_SERVER['SCRIPT_NAME'] ?? '')), '/\\');
$downloadUrl = $protocol . '://' . $host . $basePath . '/getfile.php?id='
    . $code->encrypt('CUCKOO', $email) . '&code=' . $code->encrypt($email, $filea);

$emailcontent = "Dear {$title} {$firstname} {$lastname},<br>{$affiliation}<br>{$country}<br><br>"
    . "Thanks for your interest in qPTM. Please download the dataset using the link below:<br><br>"
    . "{$datasetLabel}:<br><a href=\"{$downloadUrl}\">{$downloadUrl}</a><br><br>"
    . "Yours sincerely,<br>Professor, Ze-xian Liu<br>Sun Yat-sen University Cancer Center<br><br>"
    . "Building 2#20F, 651 Dongfeng East Road, <br>Guangzhou 510060, P. R. China<br>"
    . "Tel/Fax: +86-20-87342025<br>Personal website: http://lzx.cool";

$mail = new MySendMail();
$mail->setServer('smtp.qq.com', 'lzxlab@foxmail.com', 'wdjawtlobnppeacc', 465, true);
$mail->setFrom('lzxlab@foxmail.com');
$mail->setReceiver($email);
$mail->setCc('hujm1@sysucc.org.cn');
$mail->setMail('Download dataset from qPTM', $emailcontent);

$sent = $mail->sendMail();
if (!$sent) {
    $errorMsg = $mail->error();
    if (strpos($errorMsg, '221 Bye') === false) {
        echo json_encode(['success' => false, 'message' => 'Failed to send email. Please contact us to request the dataset.']);
        exit;
    }
}

echo json_encode([
    'success' => true,
    'message' => 'The download link was sent to ' . $email . '. Please check your inbox.',
]);
