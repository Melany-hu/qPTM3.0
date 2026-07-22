<?php

require("./resource/email.php");
$code = new code();
//echo "{$_GET['id']}<br>{$_GET['code']}<br>";
$email = $code->decrypt("CUCKOO", $_GET["id"]);
$file = $code->decrypt($email, $_GET["code"]);
//echo "{$email}<br>{$file}<br>";

if (file_exists($file)) {

    if (FALSE!== ($handler = fopen($file, 'r')))
  {
    header('Content-Description: File Transfer');
    header('Content-Type: application/octet-stream');
    header('Content-Disposition: attachment; filename='.basename($file));
    header('Content-Transfer-Encoding: chunked'); //changed to chunked
    header('Expires: 0');
    header('Cache-Control: must-revalidate, post-check=0, pre-check=0');
    header('Pragma: public');
    //header('Content-Length: ' . filesize($file)); //Remove
    //Send the content in chunks
    while(false !== ($chunk = fread($handler,4096)))
    {
      echo $chunk;
    }
  }


    // header('Content-Description: File Transfer');
    // header('Content-Type: application/octet-stream');
    // header('Content-Disposition: attachment; filename='.basename($file));
    // header('Content-Transfer-Encoding: binary');
    // header('Expires: 0');
    // header('Cache-Control: must-revalidate, post-check=0, pre-check=0');
    // header('Pragma: public');
    // header('Content-Length: ' . filesize($file));
    // ob_clean();
    // flush();
    // readfile($file);
    exit;
}
else
{
	echo "Sorry, I couldn't find the file ({$file}) you wanted, please <a href='./about.php' target='_blank'>contact us</a> to check whether there is any error in the website.";
}

//echo "The data will be available after publication of the database manuscript.";
?>