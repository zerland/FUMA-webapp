<?php

namespace IPGAP\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\DB;
use IPGAP\SubmitJob;
use IPGAP\Http\Requests;
use IPGAP\Http\Controllers\Controller;
use Symfony\Component\Process\Process;
use View;
use Auth;
use Storage;
use File;
use JavaScript;
// use Zipper;
use Mail;
use IPGAP\User;
use IPGAP\Jobs\snp2geneProcess;

class JobController extends Controller
{
    protected $user;

    public function __construct()
    {
        // Protect this Controller
        $this->middleware('auth');

        // Store user
        $this->user = Auth::user();
    }

    public function getJobList()
    {
        $email = $this->user->email;

        if( $email){
            $results = SubmitJob::where('email', $email)
                ->orderBy('created_at', 'desc')
                ->get();
        }
        else{
            $results = array();
        }

        return response()->json($results);

    }

    public function checkJobStatus(Request $request){
      $jobID = $request->input('jobID');
      $results = DB::select('SELECT * FROM SubmitJobs WHERE jobID=?', [$jobID]);
      if(count($results)==0){
        return "Notfound";
      }else{
        foreach($results as $row){
          $status = $row->status;
          return $status;
        }
      }
    }

    public function getParams(Request $request){
      $jobID = $request->input('jobID');
      $date = date('Y-m-d H:i:s');
      DB::table('SubmitJobs') -> where('jobID', $jobID)
                        -> update(['updated_at'=>$date]);

      $filedir = config('app.jobdir').'/jobs/'.$jobID.'/';
      $params = file($filedir."params.txt");
      $posMap = preg_split("/[\t]/", chop($params[18]))[1];
      $eqtlMap = preg_split("/[\t]/", chop($params[27]))[1];

      echo "$filedir:$posMap:$eqtlMap";
    }

    public function newJob(Request $request){
      // check file type
      if(mime_content_type($_FILES["GWASsummary"]["tmp_name"])!="text/plain"){
        $jobID = null;
        return view('pages.snp2gene', ['jobID' => $jobID, 'status'=>'fileFormatGWAS']);
        // return back()->withInput(['status'=> 'fileFormat']); // parameter is not working
      }
      if($request -> hasFile('leadSNPs')){
        if(mime_content_type($_FILES["leadSNPs"]["tmp_name"])!="text/plain"){
          $jobID = null;
          return view('pages.snp2gene', ['jobID' => $jobID, 'status'=>'fileFormatLead']);
        }
      }
      if($request -> hasFile('regions')){
        if(mime_content_type($_FILES["regions"]["tmp_name"])!="text/plain"){
          $jobID = null;
          return view('pages.snp2gene', ['jobID' => $jobID, 'status'=>'fileFormatRegions']);
        }
      }

      $date = date('Y-m-d H:i:s');
      $jobID;
      $filedir;
      $email = $this->user->email;

      if($request->has("NewJobTitle")){
        $jobtitle = $request -> input('NewJobTitle');
      }else{
        $jobtitle="None";
      }

      // Create new job in database
      $submitJob = new SubmitJob;
      $submitJob->email = $email;
      $submitJob->title = $jobtitle;
      $submitJob->status = 'NEW';
      $submitJob->save();

      // Get jobID (automatically generated)
      $jobID = $submitJob->jobID;

      // create job directory
      $filedir = config('app.jobdir').'/jobs/'.$jobID;
      File::makeDirectory($filedir, $mode = 0755, $recursive = true);

      // upload input Filesystem
      $leadSNPs = "input.lead";
      $GWAS = "input.gwas";
      $regions = "input.regions";
      $leadSNPsfileup = 0;
      $GWASfileup = 0;
      $regionsfileup = 0;
      // $gwasformat = $request->input('gwasformat'); //removed this option
      $gwasformat = "Plain";

      if($request -> has('addleadSNPs')){$addleadSNPs=1;}
      else{$addleadSNPs=0;}
      if($request -> hasFile('GWASsummary')){
        $request -> file('GWASsummary')->move($filedir, $GWAS);
        $GWASfileup = 1;
      }
      if($request -> hasFile('leadSNPs')){
        $request -> file('leadSNPs')->move($filedir, $leadSNPs);
        $leadSNPsfileup = 1;
      }
      if($request -> hasFile('regions')){
        $request -> file('regions')->move($filedir, $regions);
        $regionsfileup = 1;
      }

      // get parameters
      // MHC region
      if($request -> has('MHCregion')){$exMHC=1;}
      else{$exMHC=0;}
      $extMHC = $request -> input('extMHCregion');
      if($extMHC==null){$extMHC="NA";}
      // gene type
      $genetype = implode(":", $request -> input('genetype'));
      // others
      $N = $request -> input('N');
      $leadP = $request -> input('leadP');
      $r2 = $request -> input('r2');
      $gwasP = $request -> input('gwasP');
      $pop = $request -> input('pop');
      $KGSNPs = $request -> input('KGSNPs');
      if(strcmp($KGSNPs, "Yes")==0){$KGSNPs=1;}
      else{$KGSNPs=0;}
      $maf = $request -> input('maf');
      $mergeDist = $request -> input('mergeDist');
      // $Xchr = $request -> input('Xchr');
      // if(strcmp($Xchr, "Yes")==0){$Xchr=1;}
      // else{$Xchr=0;}
      if($request -> has('posMap')){$posMap=1;}
      else{$posMap=0;}
      if($request -> has('windowCheck')){
        $posMapWindow=1;
        $posMapAnnot="NA";
      }else{
        $posMapWindow=0;
        $posMapAnnot=implode(":",$request -> input('posMapAnnot'));
      }
      $posMapWindowSize = $request -> input('posMapWindow');
      if($request -> has('posMapCADDcheck')){
        $posMapCADDth = $request -> input('posMapCADDth');
      }else{
        $posMapCADDth = 0;
      }
      if($request -> has('posMapRDBcheck')){
        $posMapRDBth = $request -> input('posMapRDBth');
      }else{
        $posMapRDBth = "NA";
      }

      if($request -> has('posMapChr15check')){
        $posMapChr15Ts = $request -> input('posMapChr15Ts');
        $posMapChr15Gts = $request -> input('posMapChr15Gts');
        if(!empty($posMapChr15Ts) && !empty($posMapChr15Gts)){
          $posMapChr15Ts = implode(":", $posMapChr15Ts);
          $posMapChr15Gts = implode(":", $posMapChr15Gts);
          $posMapChr15 = implode(":", array($posMapChr15Ts, $posMapChr15Gts));
        }else if(!empty($posMapChr15Ts)){
          $posMapChr15 = implode(":", $posMapChr15Ts);
        }else{
          $posMapChr15 = implode(":", $posMapChr15Gts);
        }
        $posMapChr15Max = $request -> input('posMapChr15Max');
        $posMapChr15Meth = $request -> input('posMapChr15Meth');
      }else{
        $posMapChr15 = "NA";
        $posMapChr15Max = "NA";
        $posMapChr15Meth = "NA";
      }

      if($request -> has('eqtlMap')){
        $eqtlMap=1;
        $eqtlMapTs = $request -> input('eqtlMapTs');
        $eqtlMapGts = $request -> input('eqtlMapGts');
        if(!empty($eqtlMapTs) && !empty($eqtlMapGts)){
          $eqtlMapTs = implode(":", $eqtlMapTs);
          $eqtlMapGts = implode(":", $eqtlMapGts);
          $eqtlMaptss = implode(":", array($eqtlMapTs, $eqtlMapGts));
        }else if(!empty($eqtlMapTs)){
          $eqtlMaptss = implode(":", $eqtlMapTs);
        }else{
          $eqtlMaptss = implode(":", $eqtlMapGts);
        }
      }else{
        $eqtlMap=0;
        $eqtlMaptss = "NA";
      }
      if($request -> has('sigeqtlCheck')){
        $sigeqtl = 1;
        $eqtlP = 1;
      }else{
        $sigeqtl = 0;
        $eqtlP = $request -> input('eqtlP');
      }

      if($request -> has('eqtlMapCADDcheck')){
        $eqtlMapCADDth = $request -> input('eqtlMapCADDth');
      }else{
        $eqtlMapCADDth = 0;
      }
      if($request -> has('eqtlMapRDBcheck')){
        $eqtlMapRDBth = $request -> input('eqtlMapRDBth');
      }else{
        $eqtlMapRDBth = "NA";
      }
      if($request -> has('eqtlMapChr15check')){
        $eqtlMapChr15Ts = $request -> input('eqtlMapChr15Ts');
        $eqtlMapChr15Gts = $request -> input('eqtlMapChr15Gts');
        if(!empty($eqtlMapChr15Ts) && !empty($eqtlMapChr15Gts)){
          $eqtlMapChr15Ts = implode(":", $eqtlMapChr15Ts);
          $eqtlMapChr15Gts = implode(":", $eqtlMapChr15Gts);
          $eqtlMapChr15 = implode(":", array($eqtlMapChr15Ts, $eqtlMapChr15Gts));
        }else if(!empty($eqtlMapChr15Ts)){
          $eqtlMapChr15 = implode(":", $eqtlMapChr15Ts);
        }else{
          $eqtlMapChr15 = implode(":", $eqtlMapChr15Gts);
        }
        $eqtlMapChr15Max = $request -> input('eqtlMapChr15Max');
        $eqtlMapChr15Meth = $request -> input('eqtlMapChr15Meth');
      }else{
        $eqtlMapChr15 = "NA";
        $eqtlMapChr15Max = "NA";
        $eqtlMapChr15Meth = "NA";
      }
      // write parameter into a file
      $paramfile = $filedir.'/params.txt';
      File::put($paramfile, "Job created\t$date\n");
      File::append($paramfile, "Job title\t$jobtitle\n");
      if($GWASfileup==1){File::append($paramfile, "input GWAS summary statistics file\t".$_FILES["GWASsummary"]["name"]."\n");}
      else{File::append($paramfile, "input GWAS summary statistics file\tNot given\n");}
      File::append($paramfile, "GWAS summary statistics file format\t$gwasformat\n");
      if($leadSNPsfileup==1){File::append($paramfile, "input lead SNPs file\t".$_FILES["leadSNPs"]["name"]."\n");}
      else{File::append($paramfile, "input lead SNPs file\tNot given\n");}
      File::append($paramfile, "Identify additional lead SNPs\t$addleadSNPs\n");
      if($regionsfileup==1){File::append($paramfile, "input genetic regions file\t".$_FILES["regions"]["name"]."\n");}
      else{File::append($paramfile, "input genetic regions file\tNot given\n");}
      File::append($paramfile, "sample size\t$N\n");
      File::append($paramfile, "exclude MHC\t$exMHC\n");
      File::append($paramfile, "extended MHC region\t$extMHC\n");
      // File::append($paramfile, "include chromosome X\t$Xchr\n");
      File::append($paramfile, "gene type\t$genetype\n");
      File::append($paramfile, "lead SNP P-value\t$leadP\n");
      File::append($paramfile, "r2\t$r2\n");
      File::append($paramfile, "GWAS tagged SNPs P-value\t$gwasP\n");
      File::append($paramfile, "Population\t$pop\n");
      File::append($paramfile, "MAF\t$maf\n");
      File::append($paramfile, "Include 1000G SNPs\t$KGSNPs\n");
      File::append($paramfile, "Interval merge max distance\t$mergeDist\n");
      File::append($paramfile, "Positional mapping\t$posMap\n");
      File::append($paramfile, "posMap Window based\t$posMapWindow\n");
      File::append($paramfile, "posMap Window size\t$posMapWindowSize\n");
      File::append($paramfile, "posMap Annotation based\t$posMapAnnot\n");
      File::append($paramfile, "posMap min CADD\t$posMapCADDth\n");
      File::append($paramfile, "posMap min RegulomeDB\t$posMapRDBth\n");
      File::append($paramfile, "posMap chromatin state filterinf tissues\t$posMapChr15\n");
      File::append($paramfile, "posMap max chromatin state\t$posMapChr15Max\n");
      File::append($paramfile, "posMap chromatin state filtering method\t$posMapChr15Meth\n");
      File::append($paramfile, "eQTL mapping\t$eqtlMap\n");
      File::append($paramfile, "eqtlMap tissues\t$eqtlMaptss\n");
      File::append($paramfile, "eqtlMap significant only\t$sigeqtl\n");
      File::append($paramfile, "eqtlMap P-value\t$eqtlP\n");
      File::append($paramfile, "eqtlMap min CADD\t$eqtlMapCADDth\n");
      File::append($paramfile, "eqtlMap min RegulomeDB\t$eqtlMapRDBth\n");
      File::append($paramfile, "eqtlMap chromatin state filterinf tissues\t$eqtlMapChr15\n");
      File::append($paramfile, "eqtlMap max chromatin state\t$eqtlMapChr15Max\n");

      $user = DB::table('users')->where('email', $email)->first();
      $this->dispatch(new snp2geneProcess($user, $jobID));
      return redirect("/snp2gene#joblist-panel");
    }

    public function annotPlot(Request $request){
      $jobID = "test";
      $jobID = $request -> input('jobID');
      $filedir = config('app.jobdir').'/jobs/'.$jobID.'/';
      $type=null;
      $rowI=null;
      if($request -> has('annotPlotSelect_leadSNP')){
        $type = "leadSNP";
        $rowI = $request -> input('annotPlotSelect_leadSNP');
      }else if($request -> has('annotPlotSelect_interval')){
        $type = "interval";
        $rowI = $request -> input('annotPlotSelect_interval');
      }
#local       file_put_contents("/media/sf_Documents/VU/Data/WebApp/test.txt", "$type $rowI"); #local

      $GWAS=0;
      $CADD=0;
      $RDB=0;
      $Chr15=0;
      $eqtl=0;
      if($request -> has('annotPlot_GWASp')){$GWAS=1;}
      if($request -> has('annotPlot_CADD')){$CADD=1;}
      if($request -> has('annotPlot_RDB')){$RDB=1;}
      if($request -> has('annotPlot_Chrom15')){
        $Chr15=1;
        $Chr15Ts = $request -> input('annotPlotChr15Ts');
        $Chr15Gts = $request -> input('annotPlotChr15Gts');
        if(!empty($Chr15Ts) && !empty($Chr15Gts)){
          $Chr15Ts = implode(":", $Chr15Ts);
          $Chr15Gts = implode(":", $Chr15Gts);
          $Chr15cells = implode(":", array($Chr15Ts, $Chr15Gts));
        }else if(!empty($Chr15Ts)){
          $Chr15cells = implode(":", $Chr15Ts);
        }else{
          $Chr15cells = implode(":", $Chr15Gts);
        }
      }else{
        $Chr15cells="NA";
      }
      if($request -> has('annotPlot_eqtl')){$eqtl=1;}

      $script = storage_path()."/scripts/annotPlot.R";
      exec("Rscript $script $filedir $type $rowI $GWAS $CADD $RDB $eqtl $Chr15 $Chr15cells");

      if($Chr15==1){
        $script = storage_path()."/scripts/getChr15.pl";
        exec("$script $filedir $Chr15cells");
      }

      $eqtlplot = 0;
      $eqtlNgenes = 0;
      if($eqtl==1){
        $eqtlfile = fopen($filedir."eqtlplot.txt", 'r');
        $eqtlcheck = 0;
        fgetcsv($eqtlfile, 0, "\t");
        $eqtlgenes = array();
        while($row = fgetcsv($eqtlfile, 0, "\t")){
          $eqtlgenes[] = $row[0];
        }
        if(empty($eqtlgenes)){$eqtplot=0;}
        else{$eqtlplot=1;}
        $eqtlgenes = array_unique($eqtlgenes);
        $eqtlNgenes = count($eqtlgenes);
      }

      $xmin=null;
      $xmax=null;
      $chr=null;
      $f = $filedir."annotPlot.txt";
      $file = fopen($f, 'r');
      fgetcsv($file, 0, "\t");
      while($row=fgetcsv($file, 0, "\t")){
        if($chr==null){$chr=$row[1];}
        if($xmin==null){
          $xmin=$row[2];
          $xmax=$row[2];
        }
        if($row[2]>$xmax){$xmax=$row[2];}
      }
      fclose($file);
      $xmin_init=$xmin;
      $xmax_init=$xmax;

      $f = $filedir."genesplot.txt";
      $file = fopen($f, 'r');
      fgetcsv($file, 0, "\t");
      while($row=fgetcsv($file, 0, "\t")){
        if($xmin>$row[2]){
          $xmin=$row[2];
        }
        if($row[3]>$xmax){$xmax=$row[3];}
      }
      fclose($file);

      JavaScript::put([
        'jobID'=>$jobID,
        'filedir'=>$filedir,
        'type'=>$type,
        'rowI'=>$rowI,
        'chr'=>$chr,
        'GWASplot'=>$GWAS,
        'CADDplot'=>$CADD,
        'RDBplot'=>$RDB,
        'Chr15'=>$Chr15,
        'Chr15cells'=>$Chr15cells,
        'eqtl'=>$eqtl,
        'eqtlplot'=>$eqtlplot,
        'eqtlNgenes'=>$eqtlNgenes,
        'xMin'=>$xmin,
        'xMax'=>$xmax,
        'xMin_init'=>$xmin_init,
        'xMax_init'=>$xmax_init
      ]);
      return view('pages.annotPlot', ['jobID'=>$jobID]);
    }

    public function filedown(Request $request){
      $jobID = $request -> input('jobID');
      $filedir = config('app.jobdir').'/jobs/'.$jobID.'/';
      // $zip = new ZipArchive();
      $files = array();
      if($request -> has('paramfile')){ $files[] = $filedir."params.txt";}
      if($request -> has('leadfile')){$files[] = $filedir."leadSNPs.txt";}
      if($request -> has('intervalfile')){$files[] = $filedir."intervals.txt";}
      if($request -> has('snpsfile')){$files[] = $filedir."snps.txt"; $files[] = $filedir."ld.txt";}
      if($request -> has('annovfile')){$files[] = $filedir."annov.txt";}
      if($request -> has('annotfile')){$files[] = $filedir."annot.txt";}
      if($request -> has('genefile')){$files[] = $filedir."genes.txt";}
      if($request -> has('eqtlfile')){$files[] = $filedir."eqtl.txt";}
      // if($request -> has('exacfile')){$files[] = $filedir."ExAC.txt";}
      if($request -> has('gwascatfile')){$files[] = $filedir."gwascatalog.txt";}
      $zip = new \ZipArchive();
      $zipfile = $filedir."IPGAP.zip";

      if(File::exists($zipfile)){
        File::delete($zipfile);
      }
      // Zipper::make($zipfile)->add($files);
      // sleep(5);
      $zip -> open($zipfile, \ZipArchive::CREATE);
      foreach($files as $f){
        $zip->addFile($f);
      }
      $zip -> close();
      return response() -> download($zipfile);
    }

    public function gene2funcSubmit(Request $request){
      $id = uniqid();
      $filedir = config('app.jobdir').'/jobs/'.$id.'/';
      File::makeDirectory($filedir);
      $filedir = $filedir.'/';
      #$id = "gene2func";
      #$filedir = storage_path().'/jobs/gene2func/';

      if($request -> has('genes')){
        $gtype = "text";
        $gval = $request -> input('genes');
        $gval = preg_split('/[\n\r]+/', $gval);
        $gval = implode(':', $gval);
        // file_put_contents('/media/sf_Documents/VU/Data/WebApp/test.txt', $gval);
      }else{
        $gtype = "file";
        $gval = "genesQuery.txt";
        $request -> file('genesfile')->move($filedir, "genesQuery.txt");
      }

      if($request -> has('genetype')){
        $bkgtype = "select";
        $bkgval = $request -> input('genetype');
        $bkgval = implode(':', $bkgval);
      }else if($request -> has('bkgenes')){
        $bkgtype = "text";
        $bkgval = $request -> input('bkgenes');
        $bkgval = preg_split('/[\n\r]+/', $bkgval);
        $bkgval = implode(':', $bkgval);
      }else{
        $bkgtype ="file";
        $bkgval = "bkgenes.txt";
        $request -> file('bkgenesfile') -> move($filedir, "bkgenes.txt");
      }

      // if($request -> has('Xchr')){
      //   $Xchr = 1;
      // }else{
      //   $Xchr = 0;
      // }

      if($request -> has('MHC')){
        $MHC = 1;
      }else{
        $MHC = 0;
      }
      // echo "<p>gtype: $gtype<br/>gval: $gval<br/>bkgtype: $bkgtype<br/>bkgval: $bkgval</p>";

      $adjPmeth = $request -> input('adjPmeth');
      $adjPcut = $request -> input('adjPcut');
      $minOverlap = $request -> input('minOverlap');

      JavaScript::put([
        'id' => $id,
        'filedir' => $filedir,
        'gtype' => $gtype,
        'gval' => $gval,
        'bkgtype' => $bkgtype,
        'bkgval' => $bkgval,
        // 'Xchr' => $Xchr,
        'MHC' => $MHC,
        'adjPmeth' => $adjPmeth,
        'adjPcut' => $adjPcut,
        'minOverlap' => $minOverlap
      ]);

      return view('pages.gene2func', ['status'=>'query', 'id'=>'gene2func']);
    }

    public function geneQuery(Request $request){
      $filedir = $request -> input('filedir');
      $gtype = $request -> input('gtype');
      $gval = $request -> input('gval');
      $bkgtype = $request -> input('bkgtype');
      $bkgval = $request -> input('bkgval');
      // $Xchr = $request -> input('Xchr');
      $MHC = $request -> input('MHC');
      $adjPmeth = $request -> input('adjPmeth');
      $adjPcut = $request -> input('adjPcut');
      $minOverlap = $request -> input('minOverlap');

      $script = storage_path()."/scripts/gene2func.R";
      exec("Rscript $script $filedir $gtype $gval $bkgtype $bkgval $MHC");
      $script = storage_path()."/scripts/GeneSet.py";
      exec("$script $filedir $gtype $gval $bkgtype $bkgval $MHC $adjPmeth $adjPcut $minOverlap");
    }

    public function snp2geneGeneQuery(Request $request){
      $jobID = $request -> input('jobID');
      $filedir = config('app.jobdir').'/jobs/'.$jobID.'/';
      $gtype="text";
      $bkgtype="select";

      $params = file($filedir."params.txt");
      // $Xchr = preg_split("/[\t]/", chop($params[9]))[1];
      $MHC = preg_split("/[\t]/", chop($params[8]))[1];
      $bkgval = preg_split("/[\t]/", chop($params[10]))[1];
      $adjPmeth = "fdr_bh";
      $adjPcut = 0.05;
      $minOverlap = 2;

      $gval = null;
      $f = fopen($filedir."genes.txt", 'r');
      fgetcsv($f, 0, "\t");
      while($row = fgetcsv($f, 0, "\t")){
        if($gval==null){
          $gval = $row[0];
        }else{
          $gval = $gval.":".$row[0];
        }
      }

      JavaScript::put([
        'id' => $jobID,
        'filedir' => $filedir,
        'gtype' => $gtype,
        'gval' => $gval,
        'bkgtype' => $bkgtype,
        'bkgval' => $bkgval,
        // 'Xchr' => $Xchr,
        'MHC' => $MHC,
        'adjPmeth' => $adjPmeth,
        'adjPcut' => $adjPcut,
        'minOverlap' => $minOverlap
      ]);

       return view('pages.gene2func', ['status'=>'query', 'id'=>$jobID]);

    }

    public function SelectOption(Request $request){
      $type = $request -> input('type');
      $domain = $request -> input('domain');
      $chapter = $request -> input('chapter');
      $subchapter = $request -> input('subchapter');

      if(strcmp($type, 'Domain')==0){
        if($domain==null){
          $Domain = [];
          $results = DB::select('SELECT * FROM gwasDB');
          foreach($results as $row){
            $d = $row->Domain;
            if(array_key_exists($d, $Domain)){
              $Domain[$d] += 1;
            }else{
              $Domain[$d] = 1;
            }
          }
          // $keys = array_keys($Domain);
          // $json = "";
          // foreach($keys as $k){
          //   if(strcmp($json, "")==0){
          //     $json = '{0:"'.$k.'", 1:'.$Domain[$k].'}';
          //   }else{
          //     $json .= ',{0:"'.$k.'", 1:'.$Domain[$k].'}';
          //   }
          // }
          // $json = '{Domain:['.$json.']}';
          $json = array("Domain" => $Domain);
          // $json = json_encode($json);
          echo json_encode($json);
        }else{
          $results = DB::select('SELECT * FROM gwasDB WHERE Domain=?', [$domain]);
          $Chapter = [];
          $Subchapter = [];
          $Trait = [];
          foreach($results as $row){
            $c = $row->ChapterLevel;
            $s = $row->SubchapterLevel;
            $t = $row->Trait;
            if(array_key_exists($c, $Chapter)){
              $Chapter[$c] += 1;
            }else{
              $Chapter[$c] = 1;
            }
            if(array_key_exists($s, $Subchapter)){
              $Subchapter[$s] += 1;
            }else{
              $Subchapter[$s] = 1;
            }
            if(array_key_exists($t, $Trait)){
              $Trait[$t] += 1;
            }else{
              $Trait[$t] = 1;
            }
          }
          $json = array("Chapter"=>$Chapter, "Subchapter"=>$Subchapter, "Trait"=>$Trait);
          echo json_encode($json);
        }

      }else if(strcmp($type, 'Chapter')==0){
        if($chapter==null){
          $results = DB::select('SELECT * FROM gwasDB WHERE Domain=?', [$domain]);
          $Chapter = [];
          $Subchapter = [];
          $Trait = [];
          foreach($results as $row){
            $c = $row->ChapterLevel;
            $s = $row->SubchapterLevel;
            $t = $row->Trait;
            if(array_key_exists($c, $Chapter)){
              $Chapter[$c] += 1;
            }else{
              $Chapter[$c] = 1;
            }
            if(array_key_exists($s, $Subchapter)){
              $Subchapter[$s] += 1;
            }else{
              $Subchapter[$s] = 1;
            }
            if(array_key_exists($t, $Trait)){
              $Trait[$t] += 1;
            }else{
              $Trait[$t] = 1;
            }
          }
          $json = array("Chapter"=>$Chapter, "Subchapter"=>$Subchapter, "Trait"=>$Trait);
          echo json_encode($json);
        }else{
          $results = DB::select('SELECT * FROM gwasDB WHERE Domain=? AND ChapterLevel=?', [$domain, $chapter]);
          $Subchapter = [];
          $Trait = [];
          foreach($results as $row){
            $s = $row->SubchapterLevel;
            $t = $row->Trait;
            if(array_key_exists($s, $Subchapter)){
              $Subchapter[$s] += 1;
            }else{
              $Subchapter[$s] = 1;
            }
            if(array_key_exists($t, $Trait)){
              $Trait[$t] += 1;
            }else{
              $Trait[$t] = 1;
            }
          }
          $json = array("Subchapter"=>$Subchapter, "Trait"=>$Trait);
          echo json_encode($json);
        }
      }else if(strcmp($type, 'Subchapter')==0){
        if($chapter==null && $subchapter==null){
          $results = DB::select('SELECT * FROM gwasDB WHERE Domain=?', [$domain]);
          $Chapter = [];
          $Subchapter = [];
          $Trait = [];
          foreach($results as $row){
            $c = $row->ChapterLevel;
            $s = $row->SubchapterLevel;
            $t = $row->Trait;
            if(array_key_exists($c, $Chapter)){
              $Chapter[$c] += 1;
            }else{
              $Chapter[$c] = 1;
            }
            if(array_key_exists($s, $Subchapter)){
              $Subchapter[$s] += 1;
            }else{
              $Subchapter[$s] = 1;
            }
            if(array_key_exists($t, $Trait)){
              $Trait[$t] += 1;
            }else{
              $Trait[$t] = 1;
            }
          }
          $json = array("Chapter"=>$Chapter, "Subchapter"=>$Subchapter, "Trait"=>$Trait);
          echo json_encode($json);
        }
        else if($subchapter==null){
          $results = DB::select('SELECT * FROM gwasDB WHERE Domain=? AND ChapterLevel=?', [$domain, $chapter]);
          $Subchapter = [];
          $Trait = [];
          foreach($results as $row){
            $s = $row->SubchapterLevel;
            $t = $row->Trait;
            if(array_key_exists($s, $Subchapter)){
              $Subchapter[$s] += 1;
            }else{
              $Subchapter[$s] = 1;
            }
            if(array_key_exists($t, $Trait)){
              $Trait[$t] += 1;
            }else{
              $Trait[$t] = 1;
            }
          }
          $json = array("Subchapter"=>$Subchapter, "Trait"=>$Trait);
          echo json_encode($json);
        }else{
          $results = DB::select('SELECT * FROM gwasDB WHERE Domain=? AND SubchapterLevel=?', [$domain, $subchapter]);
          $Trait = [];
          foreach($results as $row){
            $t = $row->Trait;
            if(array_key_exists($t, $Trait)){
              $Trait[$t] += 1;
            }else{
              $Trait[$t] = 1;
            }
          }
          $json = array("Trait"=>$Trait);
          echo json_encode($json);
        }
      }else{

      }

    }

    public function selectTable(Request $request){
      $type = $request -> input('type');
      $domain = $request -> input('domain');
      $chapter = $request -> input('chapter');
      $subchapter = $request -> input('subchapter');
      $trait = $request -> input('trait');

      if(strcmp($domain, "null")==0 || (strcmp($domain, "null")==0 && strcmp($chapter, "null")==0 && strcmp($subchapter, "null")==0 && strcmp($trait, "null")==0)){
        echo '{"data":[]}';
      }else{
        $query = 'SELECT ID,PMID,Year,Domain,ChapterLevel,SubchapterLevel,Trait,Ncase,Ncontrol,N,Population,SNPh2,website FROM gwasDB WHERE';
        $head = ['ID','PMID','Year','Domain','ChapterLevel','SubchapterLevel','Trait','Ncase','Ncontrol','N','Population','SNPh2','website'];
        $val = [];
        if(strcmp($domain, "null")!=0){
          $query .= ' Domain=?';
          $val[] = $domain;
        }
        if(strcmp($chapter, "null")!=0 && strcmp($type, "Domain")!=0){
          if(count($val)!=0){$query .= " AND";}
          $query .= ' ChapterLevel=?';
          $val[] = $chapter;
        }
        if(strcmp($subchapter, "null")!=0 && strcmp($type, "Domain")!=0 && strcmp($type, "Chapter")!=0){
          if(count($val)!=0){$query .= " AND";}
          $query .= ' SubchapterLevel=?';
          $val[] = $subchapter;
        }
        if(strcmp($trait, "null")!=0 && strcmp($type, "Domain")!=0 && strcmp($type, "Chapter")!=0 && strcmp($type, "Subchapter")!=0){
          if(count($val)!=0){$query .= " AND";}
          $query .= ' Trait=?';
          $val[] = $trait;
        }
        $results = DB::select($query, $val);
        $results = json_decode(json_encode($results), true);
        $all_row = array();
        foreach($results as $row){
          $all_row[] = array_combine($head, $row);
        }
        $json = array('data'=>$all_row);
        echo json_encode($json);
      }
    }

    public function gwasDBtable(Request $request){
      $dbName = $request -> input('dbName');
      $head = DB::getSchemaBuilder()->getColumnListing('gwasDB');
      $head[8] = "ChapterLevel";
      $head[9] = "SubchapterLevel";
      $head[11] = "Nsample";
      $head[15] = "SNPh2";
      $results = DB::select('SELECT * FROM gwasDB WHERE dbName=?', [$dbName]);
      $rows = json_decode(json_encode($results), true);
      #$results = $results->toArray();
      // $f = fopen()
      // file_put_contents("/media/sf_Documents/VU/Data/WebApp/test.txt", implode(":",$rows[0]));
      $all_row = array();
      $all_row[] = array_combine($head, $rows[0]);
      $json = array('data'=>$all_row);
#local       // file_put_contents("/media/sf_Documents/VU/Data/WebApp/test.txt", json_encode($all_row));#local
      // foreach($results as $row){
      //   if($row->title==$jobtitle){
      //     $exists = true;
      //     $jobID = $row->jobID;
      //     break;
      //   }
      // }
      // file_put_contents("/media/sf_Documents/VU/Data/WebApp/test.txt", json_encode($all_row));

      // $file = fopen("/media/sf_Documents/VU/Data/gwasDB/old.txt", 'r');
      // $head = fgetcsv($file, 0, "\t");
      // $all_row = array();
      // while($row = fgetcsv($file, 0, "\t")){
      //   $all_row[] = array_combine($head, $row);
      // }
      // $json = array('data'=>$all_row);
      echo json_encode($json);
    }

    public function gene2funcFileDown(Request $request){
      $file = $request -> input('file');
      $id = $request -> input('id');
      $filedir = config('app.jobdir').'/jobs/'.$if.'/'.$file;
      return response() -> download($filedir);
    }

}
